from collections import Counter
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.models.assessment import Assessment, Question
from app.models.enums import ProposalStatus, ReviewAction, SubmissionStatus, UploadStatus, UserRole, validate_proposal_transition
from app.models.matching import ProposedAnswer, TeacherReview
from app.models.ocr import OCRExtraction
from app.models.submission import AnswerSheetUpload, QuestionAnswer, Submission
from app.models.user import User
from app.repositories.matching_repository import matching_repository
from app.schemas.matching import (
    AnswerMatchingResponse,
    ProposedAnswerRead,
    ProposedAnswerReviewResponse,
    TeacherApproveRequest,
    TeacherCorrectRequest,
    TeacherRejectRequest,
    TeacherReviewRead,
    UnansweredQuestionInfo,
    UnmatchedSegmentInfo,
)


class AnswerMatchingService:
    @staticmethod
    def extract_question_number(segment: Dict[str, Any]) -> Tuple[Optional[int], str]:
        """
        Deterministically extracts question number from a structured OCR segment.
        Returns (question_number, cleaned_answer_text).
        """
        text = (segment.get("text") or "").strip()

        # 1. Check explicit segment field
        if "question_number" in segment and segment["question_number"] is not None:
            try:
                num = int(segment["question_number"])
                cleaned = re.sub(
                    r"^\s*(?:question|q|ans|answer)?\s*[\(\[]?\s*" + str(num) + r"\s*[\)\]\.\:\-]\s*",
                    "",
                    text,
                    flags=re.IGNORECASE,
                ).strip()
                return num, cleaned or text
            except (ValueError, TypeError):
                pass

        # 2. Deterministic regex matching:
        # e.g., "Question 1: ...", "Q1. ...", "1. ...", "1) ...", "(1) ...", "Ans 1: ..."
        # Note: (?:\.(?!\d)) ensures decimal points or IP addresses (e.g. 203.165... or 0.1) are not parsed as question numbers
        pattern = r"^\s*(?:question|q|ans|answer)?\s*[\(\[]?\s*(\d{1,3})\s*(?:[\)\]\:\-]|(?:\.(?!\d)))\s*(.*)$"
        match = re.match(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            try:
                num = int(match.group(1))
                cleaned = match.group(2).strip()
                return num, cleaned or text
            except (ValueError, TypeError):
                pass

        return None, text

    @staticmethod
    def check_content_mismatch(
        cleaned_text: str, matched_q: Question, all_questions: List[Question]
    ) -> Optional[str]:
        """
        Checks whether the student answer content exhibits a strong mismatch against the matched question prompt,
        or matches another question in the assessment significantly better.
        Returns rejection_reason if mismatch suspected, else None.
        """
        if not cleaned_text or len(cleaned_text.strip()) < 10:
            return None

        stopwords = {
            "the", "and", "is", "for", "are", "with", "this", "that", "from", "what", "which",
            "calculate", "find", "determine", "state", "explain", "describe", "show", "give",
            "student", "answer", "question", "step", "steps", "value", "using", "then", "have",
        }

        def tokenize(text: str) -> set[str]:
            words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
            return {w for w in words if w not in stopwords}

        student_tokens = tokenize(cleaned_text)
        if not student_tokens:
            return None

        matched_prompt_tokens = tokenize(
            f"{matched_q.prompt} {matched_q.rubric or ''} {matched_q.expected_answer or ''}"
        )
        matched_overlap = len(student_tokens & matched_prompt_tokens)

        # Check if another question has substantially stronger token overlap
        for other_q in all_questions:
            if other_q.id == matched_q.id:
                continue
            other_tokens = tokenize(
                f"{other_q.prompt} {other_q.rubric or ''} {other_q.expected_answer or ''}"
            )
            other_overlap = len(student_tokens & other_tokens)
            if other_overlap >= 2 and matched_overlap == 0:
                return "CONTENT_MISMATCH_SUSPECTED"

        # Domain clash checks
        calculus_keywords = {
            "derivative", "differentiation", "differentiate", "integral", "limit", "chain", "product", "quotient"
        }
        linear_algebra_keywords = {
            "matrix", "matrices", "invertible", "determinant", "eigenvalue", "eigenvector", "rank"
        }
        physics_keywords = {
            "newton", "force", "acceleration", "velocity", "momentum", "gravity"
        }
        computer_networks_keywords = {
            "network", "networks", "subnet", "subnetting", "layer", "layers",
            "osi", "tcp", "udp", "ip", "routing", "router", "distance", "vector",
            "frame", "packet", "bandwidth", "propagation", "hops", "protocol",
            "transport", "datalink", "ethernet", "mac", "switch"
        }

        def get_domain(tokens: set[str]) -> Optional[str]:
            if tokens & calculus_keywords:
                return "calculus"
            if tokens & linear_algebra_keywords:
                return "linear_algebra"
            if tokens & physics_keywords:
                return "physics"
            if tokens & computer_networks_keywords:
                return "computer_networks"
            return None

        student_domain = get_domain(student_tokens)
        matched_domain = get_domain(matched_prompt_tokens)

        if student_domain and matched_domain and student_domain != matched_domain and matched_overlap == 0:
            return "CONTENT_MISMATCH_SUSPECTED"

        return None

    def match_answers(
        self,
        db: Session,
        submission_id: Optional[int] = None,
        upload_id: Optional[int] = None,
        assessment_id: Optional[int] = None,
    ) -> AnswerMatchingResponse:
        """
        Reads OCR extraction for submission upload and proposes matches for questions.
        Deterministic rules:
        - Numbers must exist and fall within 1..total_questions.
        - Duplicate question claims are routed to needs_review.
        - Existing answers or teacher reviews prevent auto-assignment (needs_review).
        - Low confidence is routed to needs_review.
        """
        if submission_id is None:
            if upload_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Either submission_id or upload_id must be provided.",
                )
            target_upload = db.query(AnswerSheetUpload).filter(AnswerSheetUpload.id == upload_id).first()
            if not target_upload:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Answer sheet upload with id {upload_id} not found.",
                )
            submission_id = target_upload.submission_id

        # 1. Validate submission exists
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission with id {submission_id} not found.",
            )

        # If an explicit assessment_id was requested and differs from submission.assessment_id, re-bind upload
        if assessment_id is not None and assessment_id != submission.assessment_id:
            target_assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
            if not target_assessment:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Target assessment with id {assessment_id} not found.",
                )
            new_sub = Submission(
                assessment_id=assessment_id,
                student_id=submission.student_id,
                status=SubmissionStatus.SUBMITTED.value,
            )
            db.add(new_sub)
            db.flush()
            if upload_id is not None:
                target_upload = db.query(AnswerSheetUpload).filter(AnswerSheetUpload.id == upload_id).first()
                if target_upload:
                    target_upload.submission_id = new_sub.id
                    db.flush()
            submission = new_sub
            submission_id = new_sub.id


        # 2. Retrieve assessment questions
        questions: List[Question] = (
            db.query(Question)
            .filter(Question.assessment_id == submission.assessment_id)
            .order_by(Question.id.asc())
            .all()
        )
        if not questions:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"No questions found for assessment id {submission.assessment_id}.",
            )

        seq_to_question = {i + 1: q for i, q in enumerate(questions)}
        qid_to_seq = {q.id: i + 1 for i, q in enumerate(questions)}

        # 3. Locate target upload and latest OCR extraction
        if upload_id is not None:
            upload = (
                db.query(AnswerSheetUpload)
                .filter(
                    AnswerSheetUpload.id == upload_id,
                    AnswerSheetUpload.submission_id == submission.id,
                )
                .first()
            )
            if not upload:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Answer sheet upload with id {upload_id} not found for submission {submission_id}.",
                )
        else:
            upload = (
                db.query(AnswerSheetUpload)
                .filter(AnswerSheetUpload.submission_id == submission.id)
                .order_by(AnswerSheetUpload.id.desc())
                .first()
            )
            if not upload:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No answer sheet uploads found for submission {submission_id}.",
                )

        extraction = (
            db.query(OCRExtraction)
            .filter(OCRExtraction.upload_id == upload.id)
            .order_by(OCRExtraction.id.desc())
            .first()
        )
        if not extraction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No OCR extraction found for upload {upload.id}. Run OCR process first.",
            )
        if extraction.processing_status == UploadStatus.FAILED.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot match answers: OCR extraction for upload {upload.id} failed.",
            )

        # 4. Check existing authoritative answers
        existing_qas = {
            qa.question_id: qa
            for qa in submission.answers
            if qa.answer_text and qa.answer_text.strip()
        }

        # 5. Parse segments
        raw_segments: List[Dict[str, Any]] = extraction.structured_segments or []
        parsed_items: List[Dict[str, Any]] = []
        for seg in raw_segments:
            q_num, cleaned_text = self.extract_question_number(seg)
            parsed_items.append(
                {
                    "segment": seg,
                    "segment_id": seg.get("segment_id"),
                    "page": seg.get("page", 1),
                    "confidence": seg.get("confidence"),
                    "q_num": q_num,
                    "cleaned_text": cleaned_text,
                    "raw_text": seg.get("text", ""),
                }
            )

        # Count frequencies of detected question numbers for ambiguity/duplicate detection
        number_counts = Counter(item["q_num"] for item in parsed_items if item["q_num"] is not None)

        proposals_out: List[ProposedAnswer] = []
        unmatched_segments_out: List[UnmatchedSegmentInfo] = []
        cleanly_matched_qids: set[int] = set()

        for item in parsed_items:
            q_num = item["q_num"]
            cleaned_text = item["cleaned_text"]
            confidence = item["confidence"]
            seg_id = item["segment_id"]

            # Case A: No question label found
            if q_num is None:
                prop = matching_repository.upsert_proposal(
                    db=db,
                    submission_id=submission.id,
                    upload_id=upload.id,
                    ocr_extraction_id=extraction.id,
                    question_id=None,
                    segment_id=seg_id,
                    proposed_text=item["raw_text"],
                    confidence=confidence,
                    status=ProposalStatus.UNMATCHED,
                    rejection_reason="NO_QUESTION_NUMBER_DETECTED",
                )
                proposals_out.append(prop)
                unmatched_segments_out.append(
                    UnmatchedSegmentInfo(
                        segment_id=seg_id,
                        page=item["page"],
                        text=item["raw_text"],
                        confidence=confidence,
                        reason="No question number detected in segment",
                    )
                )
                continue

            # Case B: Duplicate question claims among segments
            if number_counts[q_num] > 1:
                cand_question = seq_to_question.get(q_num)
                cand_qid = cand_question.id if cand_question else None
                prop = matching_repository.upsert_proposal(
                    db=db,
                    submission_id=submission.id,
                    upload_id=upload.id,
                    ocr_extraction_id=extraction.id,
                    question_id=cand_qid,
                    segment_id=seg_id,
                    proposed_text=cleaned_text,
                    confidence=confidence,
                    status=ProposalStatus.NEEDS_REVIEW,
                    rejection_reason="DUPLICATE_QUESTION_NUMBER",
                )
                proposals_out.append(prop)
                continue

            # Case C: Question number out of bounds
            if q_num not in seq_to_question:
                prop = matching_repository.upsert_proposal(
                    db=db,
                    submission_id=submission.id,
                    upload_id=upload.id,
                    ocr_extraction_id=extraction.id,
                    question_id=None,
                    segment_id=seg_id,
                    proposed_text=item["raw_text"],
                    confidence=confidence,
                    status=ProposalStatus.UNMATCHED,
                    rejection_reason="QUESTION_NUMBER_OUT_OF_BOUNDS",
                )
                proposals_out.append(prop)
                unmatched_segments_out.append(
                    UnmatchedSegmentInfo(
                        segment_id=seg_id,
                        page=item["page"],
                        text=item["raw_text"],
                        confidence=confidence,
                        reason=f"Detected question number {q_num} does not exist in assessment",
                    )
                )
                continue

            # Case D: Clean question candidate match
            matched_q = seq_to_question[q_num]
            # Ensure matched question belongs to assessment
            if matched_q.assessment_id != submission.assessment_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Question {matched_q.id} does not belong to assessment {submission.assessment_id}.",
                )

            # Check if answer already exists or content mismatch is suspected
            content_mismatch_reason = self.check_content_mismatch(cleaned_text, matched_q, questions)

            if matched_q.id in existing_qas:
                status_choice = ProposalStatus.NEEDS_REVIEW
                reason = "EXISTING_ANSWER_PRESENT"
            elif content_mismatch_reason:
                status_choice = ProposalStatus.NEEDS_REVIEW
                reason = content_mismatch_reason
            elif confidence is not None and confidence < settings.OCR_LOW_CONFIDENCE_THRESHOLD:
                status_choice = ProposalStatus.NEEDS_REVIEW
                reason = "LOW_OCR_CONFIDENCE"
            else:
                status_choice = ProposalStatus.PROPOSED
                reason = None
                cleanly_matched_qids.add(matched_q.id)

            prop = matching_repository.upsert_proposal(
                db=db,
                submission_id=submission.id,
                upload_id=upload.id,
                ocr_extraction_id=extraction.id,
                question_id=matched_q.id,
                segment_id=seg_id,
                proposed_text=cleaned_text,
                confidence=confidence,
                status=status_choice,
                rejection_reason=reason,
            )
            proposals_out.append(prop)

        # 6. Unanswered questions in assessment
        unanswered_questions_out: List[UnansweredQuestionInfo] = []
        for q in questions:
            if q.id not in cleanly_matched_qids:
                existing_qa = existing_qas.get(q.id)
                unanswered_questions_out.append(
                    UnansweredQuestionInfo(
                        question_id=q.id,
                        sequence_number=qid_to_seq[q.id],
                        prompt=q.prompt,
                        marks=q.marks,
                        has_existing_answer=existing_qa is not None,
                        existing_answer_text=existing_qa.answer_text if existing_qa else None,
                    )
                )

        matched_count = sum(1 for p in proposals_out if p.status == ProposalStatus.PROPOSED.value)
        needs_review_count = sum(1 for p in proposals_out if p.status == ProposalStatus.NEEDS_REVIEW.value)
        unmatched_count = len(unmatched_segments_out)

        logger.info(
            f"Matched answers for submission {submission_id} (upload {upload.id}): "
            f"{matched_count} proposed, {needs_review_count} needs_review, {unmatched_count} unmatched."
        )

        return AnswerMatchingResponse(
            submission_id=submission.id,
            upload_id=upload.id,
            assessment_id=submission.assessment_id,
            total_questions=len(questions),
            matched_count=matched_count,
            needs_review_count=needs_review_count,
            unmatched_count=unmatched_count,
            proposals=[ProposedAnswerRead.model_validate(p) for p in proposals_out],
            unmatched_segments=unmatched_segments_out,
            unanswered_questions=unanswered_questions_out,
        )

    def get_submission_proposals(
        self, db: Session, submission_id: int
    ) -> AnswerMatchingResponse:
        """
        Retrieves existing proposed answers for a submission's latest upload or triggers matching if none exist yet.
        Guarantees that a new upload to a submission never returns stale proposals from an older upload.
        """
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission with id {submission_id} not found.",
            )

        latest_upload = (
            db.query(AnswerSheetUpload)
            .filter(AnswerSheetUpload.submission_id == submission_id)
            .order_by(AnswerSheetUpload.id.desc())
            .first()
        )

        if latest_upload:
            upload_id = latest_upload.id
            proposals = matching_repository.get_proposals_by_upload(db=db, upload_id=latest_upload.id)
            if not proposals:
                return self.match_answers(db=db, submission_id=submission_id, upload_id=latest_upload.id)
        else:
            proposals = matching_repository.get_proposals_by_submission(db=db, submission_id=submission_id)
            if not proposals:
                return self.match_answers(db=db, submission_id=submission_id)
            upload_id = proposals[0].upload_id

        questions = (
            db.query(Question)
            .filter(Question.assessment_id == submission.assessment_id)
            .order_by(Question.id.asc())
            .all()
        )
        qid_to_seq = {q.id: i + 1 for i, q in enumerate(questions)}
        existing_qas = {qa.question_id: qa for qa in submission.answers if qa.answer_text}

        unmatched_segments: List[UnmatchedSegmentInfo] = []
        cleanly_matched: set[int] = set()

        for p in proposals:
            if p.status == ProposalStatus.UNMATCHED.value:
                unmatched_segments.append(
                    UnmatchedSegmentInfo(
                        segment_id=p.segment_id,
                        text=p.proposed_text,
                        confidence=p.confidence,
                        reason=p.rejection_reason or "Unmatched",
                    )
                )
            elif p.status in [ProposalStatus.PROPOSED.value, ProposalStatus.APPROVED.value, ProposalStatus.CORRECTED.value]:
                if p.question_id:
                    cleanly_matched.add(p.question_id)

        unanswered: List[UnansweredQuestionInfo] = []
        for q in questions:
            if q.id not in cleanly_matched:
                existing_qa = existing_qas.get(q.id)
                unanswered.append(
                    UnansweredQuestionInfo(
                        question_id=q.id,
                        sequence_number=qid_to_seq[q.id],
                        prompt=q.prompt,
                        marks=q.marks,
                        has_existing_answer=existing_qa is not None,
                        existing_answer_text=existing_qa.answer_text if existing_qa else None,
                    )
                )

        matched_count = sum(1 for p in proposals if p.status in [ProposalStatus.PROPOSED.value, ProposalStatus.APPROVED.value, ProposalStatus.CORRECTED.value])
        needs_review_count = sum(1 for p in proposals if p.status == ProposalStatus.NEEDS_REVIEW.value)

        return AnswerMatchingResponse(
            submission_id=submission.id,
            upload_id=upload_id,
            assessment_id=submission.assessment_id,
            total_questions=len(questions),
            matched_count=matched_count,
            needs_review_count=needs_review_count,
            unmatched_count=len(unmatched_segments),
            proposals=[ProposedAnswerRead.model_validate(p) for p in proposals],
            unmatched_segments=unmatched_segments,
            unanswered_questions=unanswered,
        )

    def _validate_reviewer(self, db: Session, reviewer_id: int) -> User:
        reviewer = db.query(User).filter(User.id == reviewer_id).first()
        if not reviewer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reviewer with id {reviewer_id} not found.",
            )
        if reviewer.role not in [UserRole.TEACHER.value, UserRole.ADMIN.value]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Reviewer user {reviewer_id} does not have the teacher or admin role.",
            )
        return reviewer

    def approve_proposal(
        self, db: Session, proposal_id: int, reviewer_id: int, request: TeacherApproveRequest
    ) -> ProposedAnswerReviewResponse:
        """
        Teacher approves a proposed answer. Updates authoritative QuestionAnswer.answer_text.
        """
        reviewer = self._validate_reviewer(db, reviewer_id)

        proposal = matching_repository.get_proposal_by_id(db, proposal_id)
        if not proposal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Proposed answer with id {proposal_id} not found.",
            )

        target_qid = request.question_id if request.question_id is not None else proposal.question_id
        if target_qid is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot approve an unmatched proposal without assigning a question.",
            )

        if proposal.status == ProposalStatus.APPROVED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Proposal is already approved.",
            )

        # Validate proposal transition
        validate_proposal_transition(proposal.status, ProposalStatus.APPROVED)

        # Validate question belongs to submission's assessment
        submission = db.query(Submission).filter(Submission.id == proposal.submission_id).first()
        question = db.query(Question).filter(Question.id == target_qid).first()
        if not question or question.assessment_id != submission.assessment_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Matched question does not belong to the submission's assessment.",
            )

        proposal.question_id = target_qid

        # 1. Create audit review record
        review_record = matching_repository.create_teacher_review(
            db=db,
            proposal_id=proposal.id,
            submission_id=proposal.submission_id,
            question_id=proposal.question_id,
            reviewer_id=reviewer.id,
            action=ReviewAction.APPROVE,
            original_text=proposal.proposed_text,
            final_text=proposal.proposed_text,
            review_notes=request.review_notes,
        )

        # 2. Update proposal status and metadata
        proposal.status = ProposalStatus.APPROVED.value
        proposal.rejection_reason = None
        proposal.reviewed_by = reviewer.id
        proposal.reviewed_at = datetime.now(timezone.utc)

        # 3. Update authoritative QuestionAnswer
        qa = (
            db.query(QuestionAnswer)
            .filter(
                QuestionAnswer.submission_id == proposal.submission_id,
                QuestionAnswer.question_id == proposal.question_id,
            )
            .first()
        )
        if qa:
            qa.answer_text = proposal.proposed_text
        else:
            qa = QuestionAnswer(
                submission_id=proposal.submission_id,
                question_id=proposal.question_id,
                answer_text=proposal.proposed_text,
            )
            db.add(qa)

        # 4. Unlink any other candidate proposals claiming this same question
        competing_proposals = (
            db.query(ProposedAnswer)
            .filter(
                ProposedAnswer.submission_id == proposal.submission_id,
                ProposedAnswer.question_id == proposal.question_id,
                ProposedAnswer.id != proposal.id,
                ProposedAnswer.status.in_([
                    ProposalStatus.PROPOSED.value,
                    ProposalStatus.NEEDS_REVIEW.value,
                ]),
            )
            .all()
        )
        for comp in competing_proposals:
            comp.question_id = None
            comp.status = ProposalStatus.UNMATCHED.value
            comp.rejection_reason = f"SUPERSEDED_BY_APPROVED_PROPOSAL_{proposal.id}"

        db.commit()
        db.refresh(proposal)
        db.refresh(qa)

        logger.info(
            f"Teacher {reviewer.id} approved proposal {proposal.id} for question {proposal.question_id}"
        )
        return ProposedAnswerReviewResponse(
            proposal=ProposedAnswerRead.model_validate(proposal),
            review=TeacherReviewRead.model_validate(review_record),
            authoritative_answer_text=qa.answer_text,
        )

    def correct_proposal(
        self, db: Session, proposal_id: int, reviewer_id: int, request: TeacherCorrectRequest
    ) -> ProposedAnswerReviewResponse:
        """
        Teacher corrects answer text and approves it.
        Preserves original OCR proposal text in audit record and updates QuestionAnswer.answer_text.
        """
        reviewer = self._validate_reviewer(db, reviewer_id)

        proposal = matching_repository.get_proposal_by_id(db, proposal_id)
        if not proposal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Proposed answer with id {proposal_id} not found.",
            )

        target_qid = request.question_id if request.question_id is not None else proposal.question_id
        if target_qid is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot correct an unmatched proposal without assigning a question.",
            )

        corrected = request.corrected_text.strip()
        if not corrected:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Corrected answer text cannot be empty.",
            )

        # Validate proposal transition
        validate_proposal_transition(proposal.status, ProposalStatus.CORRECTED)

        # Validate question belongs to submission's assessment
        submission = db.query(Submission).filter(Submission.id == proposal.submission_id).first()
        question = db.query(Question).filter(Question.id == target_qid).first()
        if not question or question.assessment_id != submission.assessment_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Target question does not belong to the submission's assessment.",
            )

        proposal.question_id = target_qid

        # 1. Create audit review record
        review_record = matching_repository.create_teacher_review(
            db=db,
            proposal_id=proposal.id,
            submission_id=proposal.submission_id,
            question_id=proposal.question_id,
            reviewer_id=reviewer.id,
            action=ReviewAction.CORRECT,
            original_text=proposal.proposed_text,
            final_text=corrected,
            review_notes=request.review_notes,
        )

        # 2. Update proposal status, corrected_text, and metadata
        proposal.status = ProposalStatus.CORRECTED.value
        proposal.corrected_text = corrected
        proposal.rejection_reason = None
        proposal.reviewed_by = reviewer.id
        proposal.reviewed_at = datetime.now(timezone.utc)

        # 3. Update authoritative QuestionAnswer
        qa = (
            db.query(QuestionAnswer)
            .filter(
                QuestionAnswer.submission_id == proposal.submission_id,
                QuestionAnswer.question_id == proposal.question_id,
            )
            .first()
        )
        if qa:
            qa.answer_text = corrected
        else:
            qa = QuestionAnswer(
                submission_id=proposal.submission_id,
                question_id=proposal.question_id,
                answer_text=corrected,
            )
            db.add(qa)

        # 4. Unlink any other candidate proposals claiming this same question
        competing_proposals = (
            db.query(ProposedAnswer)
            .filter(
                ProposedAnswer.submission_id == proposal.submission_id,
                ProposedAnswer.question_id == proposal.question_id,
                ProposedAnswer.id != proposal.id,
                ProposedAnswer.status.in_([
                    ProposalStatus.PROPOSED.value,
                    ProposalStatus.NEEDS_REVIEW.value,
                ]),
            )
            .all()
        )
        for comp in competing_proposals:
            comp.question_id = None
            comp.status = ProposalStatus.UNMATCHED.value
            comp.rejection_reason = f"SUPERSEDED_BY_CORRECTED_PROPOSAL_{proposal.id}"

        db.commit()
        db.refresh(proposal)
        db.refresh(qa)

        logger.info(
            f"Teacher {reviewer.id} corrected proposal {proposal.id} for question {proposal.question_id}"
        )
        return ProposedAnswerReviewResponse(
            proposal=ProposedAnswerRead.model_validate(proposal),
            review=TeacherReviewRead.model_validate(review_record),
            authoritative_answer_text=qa.answer_text,
        )

    def reject_proposal(
        self, db: Session, proposal_id: int, reviewer_id: int, request: TeacherRejectRequest
    ) -> ProposedAnswerReviewResponse:
        """
        Teacher rejects a proposal. Does NOT update QuestionAnswer.answer_text.
        """
        reviewer = self._validate_reviewer(db, reviewer_id)

        proposal = matching_repository.get_proposal_by_id(db, proposal_id)
        if not proposal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Proposed answer with id {proposal_id} not found.",
            )

        if proposal.status == ProposalStatus.REJECTED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Proposal is already rejected.",
            )

        # Validate proposal transition
        validate_proposal_transition(proposal.status, ProposalStatus.REJECTED)

        # 1. Create audit review record
        review_record = matching_repository.create_teacher_review(
            db=db,
            proposal_id=proposal.id,
            submission_id=proposal.submission_id,
            question_id=proposal.question_id,
            reviewer_id=reviewer.id,
            action=ReviewAction.REJECT,
            original_text=proposal.proposed_text,
            final_text=None,
            review_notes=request.review_notes,
        )

        # 2. Update proposal status
        proposal.status = ProposalStatus.REJECTED.value
        proposal.rejection_reason = request.rejection_reason or "Rejected by teacher"
        proposal.reviewed_by = reviewer.id
        proposal.reviewed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(proposal)

        logger.info(f"Teacher {reviewer.id} rejected proposal {proposal.id}")
        return ProposedAnswerReviewResponse(
            proposal=ProposedAnswerRead.model_validate(proposal),
            review=TeacherReviewRead.model_validate(review_record),
            authoritative_answer_text=None,
        )

    def get_proposal(self, db: Session, proposal_id: int) -> ProposedAnswerRead:
        proposal = matching_repository.get_proposal_by_id(db=db, proposal_id=proposal_id)
        if not proposal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Proposed answer with id {proposal_id} not found.",
            )
        return ProposedAnswerRead.model_validate(proposal)

    def get_upload_proposals(
        self, db: Session, upload_id: int
    ) -> AnswerMatchingResponse:
        upload = db.query(AnswerSheetUpload).filter(AnswerSheetUpload.id == upload_id).first()
        if not upload:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Answer sheet upload with id {upload_id} not found.",
            )
        proposals = matching_repository.get_proposals_by_upload(db=db, upload_id=upload_id)
        if not proposals:
            return self.match_answers(db=db, submission_id=upload.submission_id, upload_id=upload_id)

        submission = db.query(Submission).filter(Submission.id == upload.submission_id).first()
        if not submission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission with id {upload.submission_id} not found.",
            )

        questions = (
            db.query(Question)
            .filter(Question.assessment_id == submission.assessment_id)
            .order_by(Question.id.asc())
            .all()
        )
        qid_to_seq = {q.id: i + 1 for i, q in enumerate(questions)}
        existing_qas = {qa.question_id: qa for qa in submission.answers if qa.answer_text}

        unmatched_segments: List[UnmatchedSegmentInfo] = []
        cleanly_matched: set[int] = set()

        for p in proposals:
            if p.status == ProposalStatus.UNMATCHED.value:
                unmatched_segments.append(
                    UnmatchedSegmentInfo(
                        segment_id=p.segment_id,
                        text=p.proposed_text,
                        confidence=p.confidence,
                        reason=p.rejection_reason or "Unmatched",
                    )
                )
            elif p.status in [ProposalStatus.PROPOSED.value, ProposalStatus.APPROVED.value, ProposalStatus.CORRECTED.value]:
                if p.question_id:
                    cleanly_matched.add(p.question_id)

        unanswered: List[UnansweredQuestionInfo] = []
        for q in questions:
            if q.id not in cleanly_matched:
                existing_qa = existing_qas.get(q.id)
                unanswered.append(
                    UnansweredQuestionInfo(
                        question_id=q.id,
                        sequence_number=qid_to_seq[q.id],
                        prompt=q.prompt,
                        marks=q.marks,
                        has_existing_answer=existing_qa is not None,
                        existing_answer_text=existing_qa.answer_text if existing_qa else None,
                    )
                )

        matched_count = sum(1 for p in proposals if p.status in [ProposalStatus.PROPOSED.value, ProposalStatus.APPROVED.value, ProposalStatus.CORRECTED.value])
        needs_review_count = sum(1 for p in proposals if p.status == ProposalStatus.NEEDS_REVIEW.value)

        return AnswerMatchingResponse(
            submission_id=submission.id,
            upload_id=upload_id,
            assessment_id=submission.assessment_id,
            total_questions=len(questions),
            matched_count=matched_count,
            needs_review_count=needs_review_count,
            unmatched_count=len(unmatched_segments),
            proposals=[ProposedAnswerRead.model_validate(p) for p in proposals],
            unmatched_segments=unmatched_segments,
            unanswered_questions=unanswered,
        )


matching_service = AnswerMatchingService()

