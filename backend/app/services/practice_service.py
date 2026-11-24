from datetime import datetime
import re
from typing import Dict, List, Optional, Set, Tuple
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import (
    FindingReviewStatus,
    InvalidStateTransitionError,
    PracticeItemReviewStatus,
    PracticeQuestionType,
    PracticeSessionStatus,
    UserRole,
    validate_practice_session_transition,
)
from app.models.evaluation import EvaluationFinding, EvaluationRun
from app.models.practice import PracticeResponse, PracticeSession
from app.models.remediation import RemediationItem, RemediationRun
from app.models.submission import Submission
from app.models.user import User
from app.repositories.practice_repository import practice_repository
from app.repositories.submission_repository import submission_repository
from app.schemas.practice import (
    ConceptPracticeProgress,
    PracticeResponseRead,
    PracticeResponseSubmit,
    PracticeSessionDetailRead,
    PracticeSessionItemRead,
    PracticeSessionRead,
    PracticeSessionSummary,
)

COMMON_STOPWORDS: Set[str] = {
    "that", "this", "with", "from", "have", "were", "what", "when", "your",
    "they", "them", "then", "than", "some", "such", "into", "more", "also",
    "about", "which", "there", "their", "could", "would", "should", "will",
    "been", "being", "does", "doing", "make", "made", "like", "just", "well",
    "very", "much", "many", "most", "same", "here", "where", "while",
}

NON_ANSWER_PATTERNS: List[str] = [
    r"\bi\s*(?:do\s*not|don\s*t|don'?t)\s*know\b",
    r"\bno\s*(?:idea|clue)\b",
    r"\bnot\s*sure\b",
    r"\bhave\s*no\s*(?:clue|idea)\b",
    r"\bcan\s*(?:not|t|'?t)\s*explain\b",
    r"\bidk\b",
    r"\bunsure\b",
    r"\b(?:do\s*not|don\s*t|don'?t)\s*understand\b",
]


def _normalize_text(text: str) -> str:
    """Normalizes text for deterministic, case-insensitive comparison."""
    if not text:
        return ""
    # Lowercase, replace punctuation with space, collapse whitespace
    t = text.lower().strip()
    t = re.sub(r"[^\w\s\^\-\+\/\*]", " ", t)
    return " ".join(t.split())


class PracticeService:
    """Business logic for student practice sessions, safe delivery, and deterministic feedback."""

    def _assert_submission_access(self, submission: Submission, current_user: User) -> None:
        user_role = current_user.role.value if isinstance(current_user.role, UserRole) else str(current_user.role)
        if user_role == UserRole.STUDENT.value and submission.student_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access practice sessions for this submission.",
            )

    def _assert_session_access(self, session: PracticeSession, current_user: User) -> None:
        user_role = current_user.role.value if isinstance(current_user.role, UserRole) else str(current_user.role)
        if user_role == UserRole.STUDENT.value and session.student_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this practice session.",
            )

    def _get_approved_remediation_items(self, db: Session, submission_id: int) -> List[RemediationItem]:
        """
        Retrieves ONLY teacher-approved remediation items originating from teacher-accepted findings
        for the given submission.
        Strictly excludes rejected, pending-review, and edited-but-unapproved items.
        """
        return (
            db.query(RemediationItem)
            .join(RemediationRun, RemediationItem.run_id == RemediationRun.id)
            .join(EvaluationFinding, RemediationItem.finding_id == EvaluationFinding.id)
            .join(EvaluationRun, EvaluationFinding.run_id == EvaluationRun.id)
            .filter(
                EvaluationRun.submission_id == submission_id,
                EvaluationFinding.review_status == FindingReviewStatus.ACCEPTED.value,
                RemediationItem.review_status == PracticeItemReviewStatus.APPROVED.value,
            )
            .order_by(RemediationItem.id.asc())
            .all()
        )

    def start_practice_session(
        self, db: Session, *, submission_id: int, current_user: User, resume_active: bool = True
    ) -> PracticeSessionDetailRead:
        """
        Starts or resumes a practice session for a student's submission.
        Guarantees that only approved practice items are deliverable.
        """
        submission = submission_repository.get_by_id(db=db, submission_id=submission_id)
        if not submission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission with id {submission_id} not found.",
            )

        self._assert_submission_access(submission, current_user)

        # 1. Fetch eligible approved remediation items
        approved_items = self._get_approved_remediation_items(db, submission_id)
        if not approved_items:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No teacher-approved practice items are currently available for this submission.",
            )

        # 2. Check for active session if resume requested
        session: Optional[PracticeSession] = None
        target_student_id = submission.student_id
        if resume_active:
            session = practice_repository.get_active_session_for_submission(
                db, student_id=target_student_id, submission_id=submission_id
            )

        # 3. Create new session if no active session found
        if not session:
            session = practice_repository.create_session(
                db,
                student_id=target_student_id,
                submission_id=submission_id,
                total_items=len(approved_items),
            )

        return self._build_session_detail(db, session=session, approved_items=approved_items)

    def get_practice_session(
        self, db: Session, *, session_id: int, current_user: User
    ) -> PracticeSessionDetailRead:
        """Retrieves an existing practice session with safe deliverable items and existing responses."""
        session = practice_repository.get_session_by_id(db, session_id=session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Practice session with id {session_id} not found.",
            )

        self._assert_session_access(session, current_user)
        approved_items = self._get_approved_remediation_items(db, session.submission_id)
        return self._build_session_detail(db, session=session, approved_items=approved_items)

    def list_sessions_for_submission(
        self, db: Session, *, submission_id: int, current_user: User
    ) -> List[PracticeSessionRead]:
        """Lists practice sessions for a submission, restricted to owner student unless teacher/admin."""
        submission = submission_repository.get_by_id(db=db, submission_id=submission_id)
        if not submission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission with id {submission_id} not found.",
            )

        self._assert_submission_access(submission, current_user)
        user_role = current_user.role.value if isinstance(current_user.role, UserRole) else str(current_user.role)
        student_filter = current_user.id if user_role == UserRole.STUDENT.value else None

        sessions = practice_repository.list_sessions_for_submission(
            db, submission_id=submission_id, student_id=student_filter
        )
        return [PracticeSessionRead.model_validate(s) for s in sessions]

    def _build_session_detail(
        self, db: Session, *, session: PracticeSession, approved_items: List[RemediationItem]
    ) -> PracticeSessionDetailRead:
        """Builds a student-safe detail view, mapping existing responses and suppressing confidential data."""
        responses = practice_repository.get_responses_for_session(db, session_id=session.id)
        response_map: Dict[int, PracticeResponse] = {r.remediation_item_id: r for r in responses}

        items_out: List[PracticeSessionItemRead] = []
        for item in approved_items:
            resp = response_map.get(item.id)
            # Use effective prompt (teacher edit if provided, otherwise original generated prompt)
            prompt = item.edited_question_text or item.question_text

            items_out.append(
                PracticeSessionItemRead(
                    id=item.id,
                    finding_id=item.finding_id,
                    target_concept=item.target_concept,
                    question_text=prompt,
                    question_type=PracticeQuestionType(item.question_type),
                    options=item.options,
                    difficulty=item.difficulty,
                    answered=(resp is not None),
                    response=PracticeResponseRead.model_validate(resp) if resp else None,
                )
            )

        responses_out = [PracticeResponseRead.model_validate(r) for r in responses]

        return PracticeSessionDetailRead(
            id=session.id,
            student_id=session.student_id,
            submission_id=session.submission_id,
            status=PracticeSessionStatus(session.status),
            total_items=session.total_items,
            completed_items=session.completed_items,
            created_at=session.created_at,
            updated_at=session.updated_at,
            completed_at=session.completed_at,
            items=items_out,
            responses=responses_out,
        )

    def grade_answer(
        self, item: RemediationItem, student_answer: str
    ) -> Tuple[bool, float, str]:
        """
        Deterministically evaluates student response against effective answer key.
        Generates transparent, safe pedagogical feedback without leaking internal teacher notes.
        Handles edge cases: empty input, MCQ option letters/text, short-answer boundaries,
        negations, and explain-reasoning keyword overlap.
        """
        clean_student = student_answer.strip()
        concept = item.target_concept or "the target concept"
        raw_expected = (item.edited_answer_key or item.teacher_answer_key or "").strip()

        # 1. Reject empty or whitespace-only answers immediately
        if not clean_student:
            return False, 0.0, "No answer provided. Please enter a substantive response."

        if not raw_expected:
            return False, 0.0, "Answer key unavailable for automated evaluation."

        if item.question_type == PracticeQuestionType.MULTIPLE_CHOICE.value:
            norm_student = _normalize_text(clean_student)
            norm_expected = _normalize_text(raw_expected)

            # Strip leading "option " or "choice "
            clean_s = re.sub(r"^(?:option|choice)\s+", "", norm_student).strip()
            clean_e = re.sub(r"^(?:option|choice)\s+", "", norm_expected).strip()

            s_tokens = clean_s.split()
            e_tokens = clean_e.split()

            # Identify single letter indicators (e.g. "a", "b", "c", "d")
            s_letter = s_tokens[0] if (s_tokens and len(s_tokens[0]) == 1) else None
            e_letter = e_tokens[0] if (e_tokens and len(e_tokens[0]) == 1) else None

            is_correct = False
            if clean_s == clean_e:
                is_correct = True
            elif s_letter and e_letter and s_letter == e_letter:
                is_correct = True
            elif s_letter and clean_e.startswith(s_letter + " "):
                is_correct = True
            elif e_letter and clean_s.startswith(e_letter + " "):
                is_correct = True

            score = 1.0 if is_correct else 0.0
            feedback = (
                f"Correct! Your selection accurately applies {concept}."
                if is_correct
                else f"Incorrect. Review the core rules of {concept} and try similar practice exercises."
            )
            return is_correct, score, feedback

        elif item.question_type == PracticeQuestionType.SHORT_ANSWER.value:
            norm_student = _normalize_text(clean_student)
            norm_expected = _normalize_text(raw_expected)

            if norm_student == norm_expected:
                is_correct = True
            else:
                # Word-boundary exact phrase match
                escaped_expected = re.escape(norm_expected)
                boundary_match = bool(re.search(rf"(?:^|\s){escaped_expected}(?:$|\s)", norm_student))

                # Check for negations preceding the expected answer in the clause
                match_pos = norm_student.find(norm_expected)
                prefix = norm_student[:match_pos] if match_pos != -1 else ""
                negated_match = bool(
                    re.search(r"\b(?:not|never|neither|cannot|can\s*t|can'?t|isn\s*t|isn'?t|is\s*not)\b", prefix)
                )

                # Reject answers that are excessively long compared to expected (prompt dumping heuristic)
                excessive_length = len(norm_student.split()) > max(15, len(norm_expected.split()) * 4)

                is_correct = boundary_match and not negated_match and not excessive_length

            score = 1.0 if is_correct else 0.0
            feedback = (
                f"Correct! Your answer accurately demonstrates {concept}."
                if is_correct
                else f"Incorrect. Check your algebraic steps and review the definitions for {concept}."
            )
            return is_correct, score, feedback

        else:  # EXPLAIN_REASONING
            norm_student = _normalize_text(clean_student)
            norm_expected = _normalize_text(raw_expected)

            # 1. Non-answer / refusal detection (e.g. "I don't know", "no idea", "not sure")
            is_non_answer = any(re.search(pat, norm_student) for pat in NON_ANSWER_PATTERNS)
            if is_non_answer:
                return False, 0.0, f"Needs revision. Your explanation indicates uncertainty. Review {concept} and articulate the step-by-step reasoning."

            # 2. Length check: substantive explanation required (at least 15 characters)
            if len(clean_student) < 15:
                return False, 0.0, f"Explanation is too brief. Please provide a complete explanation of {concept}."

            # 3. Extract meaningful target keywords (length > 3, exclude common stopwords)
            expected_words = [w for w in norm_expected.split() if len(w) > 3 and w not in COMMON_STOPWORDS]
            concept_words = [w for w in _normalize_text(concept).split() if len(w) > 3 and w not in COMMON_STOPWORDS]
            target_words = set(expected_words + concept_words)

            student_words = set(norm_student.split())

            # Whole-word matches only (prevents substring confusion like 'term' matching 'intermediate')
            matched_words = target_words.intersection(student_words)
            matches = len(matched_words)

            required_matches = min(2, len(target_words)) if target_words else 0
            is_correct = matches >= required_matches

            score = 1.0 if is_correct else 0.0
            feedback = (
                f"Well explained! Your reasoning accurately articulates the principles of {concept}."
                if is_correct
                else f"Needs revision. Ensure your explanation clearly explains the underlying reasoning for {concept}."
            )
            return is_correct, score, feedback

    def submit_response(
        self, db: Session, *, session_id: int, request: PracticeResponseSubmit, current_user: User
    ) -> PracticeResponseRead:
        """
        Submits student response, enforces single submission per item, executes deterministic grading,
        persists complete provenance, and advances session state.
        """
        session = practice_repository.get_session_by_id(db, session_id=session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Practice session with id {session_id} not found.",
            )

        self._assert_session_access(session, current_user)
        if session.student_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the student who owns this practice session may submit answers.",
            )

        # 1. Validate session state
        if session.status != PracticeSessionStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot submit answers to a practice session that is '{session.status}'.",
            )

        # 2. Validate remediation item existence
        item = db.query(RemediationItem).filter(RemediationItem.id == request.remediation_item_id).first()
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Remediation item with id {request.remediation_item_id} not found.",
            )

        # 3. Validate item is approved for delivery
        if item.review_status != PracticeItemReviewStatus.APPROVED.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Practice item {item.id} is not approved for student delivery.",
            )

        # 4. Validate provenance linkage to the session's submission
        finding = db.query(EvaluationFinding).filter(EvaluationFinding.id == item.finding_id).first()
        if not finding:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated evaluation finding not found.")
        eval_run = db.query(EvaluationRun).filter(EvaluationRun.id == finding.run_id).first()
        if not eval_run or eval_run.submission_id != session.submission_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Remediation item {item.id} does not belong to the submission associated with this practice session.",
            )

        # 5. Prevent duplicate submissions for the same item in this session
        existing = practice_repository.get_response(db, session_id=session.id, remediation_item_id=item.id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Practice item {item.id} has already been answered in session {session.id}.",
            )

        # 6. Deterministic scoring and safe feedback
        is_correct, score, feedback = self.grade_answer(item, request.student_answer)

        # 7. Persist response with full provenance
        try:
            response = practice_repository.create_response(
                db,
                session_id=session.id,
                remediation_item_id=item.id,
                finding_id=finding.id,
                evaluation_run_id=eval_run.id,
                student_answer=request.student_answer,
                is_correct=is_correct,
                score=score,
                feedback=feedback,
            )
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Practice item {item.id} has already been answered in session {session.id}.",
            )

        # 8. Increment completed items and auto-complete session if all items answered
        practice_repository.increment_completed_items(db, session=session)

        return PracticeResponseRead.model_validate(response)

    def get_session_summary(
        self, db: Session, *, session_id: int, current_user: User
    ) -> PracticeSessionSummary:
        """
        Compiles transparent formative evaluation evidence and concept progress.
        Avoids unsupported claims of mastery from single responses.
        """
        session = practice_repository.get_session_by_id(db, session_id=session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Practice session with id {session_id} not found.",
            )

        self._assert_session_access(session, current_user)
        responses = practice_repository.get_responses_for_session(db, session_id=session.id)

        correct_count = sum(1 for r in responses if r.is_correct)
        total_score = sum(r.score for r in responses)
        max_score = float(session.total_items)
        accuracy = (float(correct_count) / float(session.total_items) * 100.0) if session.total_items > 0 else 0.0

        # Group by target concept
        concept_stats: Dict[str, Dict[str, int]] = {}
        for r in responses:
            item = db.query(RemediationItem).filter(RemediationItem.id == r.remediation_item_id).first()
            concept = (item.target_concept if item and item.target_concept else "General Concept")
            if concept not in concept_stats:
                concept_stats[concept] = {"total": 0, "correct": 0}
            concept_stats[concept]["total"] += 1
            if r.is_correct:
                concept_stats[concept]["correct"] += 1

        concepts_out = []
        for c, stats in concept_stats.items():
            tot = stats["total"]
            corr = stats["correct"]
            if tot == 1:
                if corr == 1:
                    o_status = "uncertain"
                    u_level = "Moderate-High"
                    rem_gap = "Single response; further evidence needed to confirm consistent problem solving."
                    next_st = "Complete at least 1 more follow-up question to solidify this concept."
                else:
                    o_status = "persisting_gap"
                    u_level = "Moderate"
                    rem_gap = f"Initial misconception regarding '{c}' is still evident in follow-up practice."
                    next_st = "Review concept explanation and discuss with instructor before retrying."
            else:
                if corr == tot:
                    o_status = "improved"
                    u_level = "Low-Moderate"
                    rem_gap = "None detected in follow-up practice; reinforce in cumulative reviews."
                    next_st = "Demonstrated consistent understanding! Ready to advance."
                elif corr == 0:
                    o_status = "persisting_gap"
                    u_level = "Low"
                    rem_gap = f"Misconception regarding '{c}' persists across {tot} attempts."
                    next_st = "Seek direct guidance from your teacher before continuing."
                else:
                    o_status = "uncertain"
                    u_level = "High"
                    rem_gap = f"Inconsistent problem solving on '{c}'."
                    next_st = "Practice 1-2 more problems to address missed steps."

            concepts_out.append(
                ConceptPracticeProgress(
                    concept_name=c,
                    items_count=tot,
                    correct_count=corr,
                    evidence_summary=f"{corr} of {tot} practice questions answered correctly.",
                    remaining_gaps=rem_gap,
                    recommended_next_step=next_st,
                    outcome_status=o_status,
                    uncertainty_level=u_level,
                )
            )

        return PracticeSessionSummary(
            session_id=session.id,
            submission_id=session.submission_id,
            status=PracticeSessionStatus(session.status),
            total_items=session.total_items,
            completed_items=session.completed_items,
            correct_count=correct_count,
            total_score=total_score,
            max_score=max_score,
            accuracy_percentage=round(accuracy, 2),
            concepts_practiced=concepts_out,
        )

    def complete_session(
        self, db: Session, *, session_id: int, current_user: User
    ) -> PracticeSessionRead:
        """Explicitly marks an active practice session as completed."""
        session = practice_repository.get_session_by_id(db, session_id=session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Practice session with id {session_id} not found.",
            )

        self._assert_session_access(session, current_user)
        try:
            validate_practice_session_transition(session.status, PracticeSessionStatus.COMPLETED)
        except InvalidStateTransitionError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(err),
            )

        session = practice_repository.update_session_status(
            db, session=session, new_status=PracticeSessionStatus.COMPLETED, completed_at=datetime.now()
        )
        return PracticeSessionRead.model_validate(session)

    def abandon_session(
        self, db: Session, *, session_id: int, current_user: User
    ) -> PracticeSessionRead:
        """Marks an active practice session as abandoned."""
        session = practice_repository.get_session_by_id(db, session_id=session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Practice session with id {session_id} not found.",
            )

        self._assert_session_access(session, current_user)
        try:
            validate_practice_session_transition(session.status, PracticeSessionStatus.ABANDONED)
        except InvalidStateTransitionError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(err),
            )

        session = practice_repository.update_session_status(
            db, session=session, new_status=PracticeSessionStatus.ABANDONED, completed_at=datetime.now()
        )
        return PracticeSessionRead.model_validate(session)


practice_service = PracticeService()
