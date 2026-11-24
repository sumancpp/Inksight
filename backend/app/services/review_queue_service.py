from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models.assessment import Assessment, Question
from app.models.enums import CorrectionFieldName, FindingCategory, FindingReviewStatus, ProposalStatus
from app.models.evaluation import EvaluationFinding, EvaluationRun
from app.models.matching import ProposedAnswer
from app.models.submission import Submission
from app.models.user import User
from app.schemas.review_queue import PendingReviewItem, PendingReviewQueueResponse
from app.services.correction_service import resolve_finding_field


class ReviewQueueService:
    def get_pending_review_queue(
        self,
        db: Session,
        assessment_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
        sort: str = "priority",
    ) -> PendingReviewQueueResponse:
        # Base query for candidate findings
        query = (
            db.query(EvaluationFinding)
            .join(EvaluationRun, EvaluationFinding.run_id == EvaluationRun.id)
            .join(Submission, EvaluationRun.submission_id == Submission.id)
            .filter(
                EvaluationFinding.review_status != FindingReviewStatus.SUPERSEDED.value,
                or_(
                    EvaluationFinding.review_status == FindingReviewStatus.PENDING_REVIEW.value,
                    and_(
                        EvaluationFinding.review_status == FindingReviewStatus.ACCEPTED.value,
                        EvaluationFinding.requires_teacher_review == True,
                        EvaluationFinding.acknowledged_uncertainty == False,
                    ),
                ),
            )
        )
        if assessment_id is not None:
            query = query.filter(Submission.assessment_id == assessment_id)

        candidate_findings: List[EvaluationFinding] = query.all()

        if not candidate_findings:
            return PendingReviewQueueResponse(
                items=[],
                total=0,
                page=page,
                page_size=page_size,
                total_pages=0,
            )

        # Collect distinct assessment IDs to compute class-wide signals & question numbering
        assessment_ids = {
            f.run.submission.assessment_id
            for f in candidate_findings
            if f.run and f.run.submission
        }
        if assessment_id is not None:
            assessment_ids.add(assessment_id)

        # Precompute question numbers per assessment (1-based index by Question.id asc)
        question_orders: Dict[int, List[int]] = {}
        for aid in assessment_ids:
            q_ids = [
                q.id
                for q in db.query(Question.id)
                .filter(Question.assessment_id == aid)
                .order_by(Question.id.asc())
                .all()
            ]
            question_orders[aid] = q_ids

        # Precompute class-wide misconception concepts per assessment:
        # Map (assessment_id, normalized_concept) -> set of distinct student_ids
        # Reads via resolve_finding_field to incorporate teacher corrections (Note C)
        concept_students: Dict[Tuple[int, str], Set[int]] = defaultdict(set)

        all_assessment_findings = (
            db.query(EvaluationFinding)
            .join(EvaluationRun, EvaluationFinding.run_id == EvaluationRun.id)
            .join(Submission, EvaluationRun.submission_id == Submission.id)
            .filter(
                Submission.assessment_id.in_(assessment_ids),
                EvaluationFinding.review_status != FindingReviewStatus.SUPERSEDED.value,
            )
            .all()
        )

        for af in all_assessment_findings:
            if not af.run or not af.run.submission:
                continue
            a_id = af.run.submission.assessment_id
            s_id = af.run.submission.student_id

            # Check resolved linked concept
            resolved_concept = resolve_finding_field(af, CorrectionFieldName.LINKED_CONCEPT)
            if resolved_concept and str(resolved_concept).strip():
                concept_students[(a_id, str(resolved_concept).strip().lower())].add(s_id)

            # Also check misconception items
            if af.misconceptions:
                for idx, m in enumerate(af.misconceptions):
                    # If first misconception and resolved_concept was corrected, first is handled
                    m_concept = m.get("linked_concept") if isinstance(m, dict) else getattr(m, "linked_concept", None)
                    if m_concept and str(m_concept).strip():
                        concept_students[(a_id, str(m_concept).strip().lower())].add(s_id)

        # Process each candidate finding
        items: List[PendingReviewItem] = []
        for finding in candidate_findings:
            run = finding.run
            submission = run.submission if run else None
            student = submission.student if submission else None
            assessment = submission.assessment if submission else None
            question = run.question if run else None

            a_id = submission.assessment_id if submission else 0
            s_id = submission.student_id if submission else 0
            q_id = run.question_id if run else 0

            # 1. Question number (1-based index within assessment)
            q_list = question_orders.get(a_id, [])
            q_num = (q_list.index(q_id) + 1) if q_id in q_list else q_id

            # 2. Priority scoring with Note C corrections resolved
            score = 0
            reasons: List[str] = []

            # Rule A: +40 if requires_teacher_review == True
            # (Note B & C: remains True after confidence correction unless explicitly reviewed)
            req_review = resolve_finding_field(finding, "requires_teacher_review")
            if req_review is None:
                req_review = finding.requires_teacher_review
            if bool(req_review) is True:
                score += 40
                reasons.append("Requires teacher review flag (+40)")

            # Rule B: +30 if any misconception hypothesis exists
            hypo = resolve_finding_field(finding, CorrectionFieldName.MISCONCEPTION_HYPOTHESIS)
            if not hypo and finding.misconceptions:
                for m in finding.misconceptions:
                    mh = m.get("hypothesis") if isinstance(m, dict) else getattr(m, "hypothesis", None)
                    if mh and str(mh).strip():
                        hypo = mh
                        break
            if hypo and str(hypo).strip():
                score += 30
                reasons.append("Misconception hypothesis detected (+30)")

            # Rule C: +20 if OCR confidence in original extraction < 0.85
            ocr_conf = resolve_finding_field(finding, "ocr_confidence")
            if ocr_conf is None and run:
                # Query approved proposal or any proposal for (submission_id, question_id)
                prop = (
                    db.query(ProposedAnswer)
                    .filter(
                        ProposedAnswer.submission_id == run.submission_id,
                        ProposedAnswer.question_id == run.question_id,
                        ProposedAnswer.status.in_([
                            ProposalStatus.APPROVED.value,
                            ProposalStatus.CORRECTED.value,
                        ]),
                    )
                    .first()
                )
                if not prop:
                    prop = (
                        db.query(ProposedAnswer)
                        .filter(
                            ProposedAnswer.submission_id == run.submission_id,
                            ProposedAnswer.question_id == run.question_id,
                        )
                        .first()
                    )
                if prop and prop.confidence is not None:
                    ocr_conf = float(prop.confidence)
                elif prop and prop.ocr_extraction and prop.ocr_extraction.confidence is not None:
                    ocr_conf = float(prop.ocr_extraction.confidence)

            if ocr_conf is not None and float(ocr_conf) < 0.85:
                score += 20
                reasons.append(f"Low OCR extraction confidence ({float(ocr_conf):.2f} < 0.85) (+20)")

            # Rule D: +10 if finding.category == "INSUFFICIENT_EVIDENCE"
            cat_val = resolve_finding_field(finding, "category") or finding.category
            cat_str = cat_val.value if hasattr(cat_val, "value") else str(cat_val)
            if cat_str.upper() in ("INSUFFICIENT_EVIDENCE", "FINDINGCATEGORY.INSUFFICIENT_EVIDENCE"):
                score += 10
                reasons.append("Insufficient evidence category (+10)")

            # Rule E: +5 * number of misconception items
            m_count = len(finding.misconceptions or [])
            if m_count == 0 and hypo and str(hypo).strip():
                m_count = 1
            if m_count > 0:
                score += 5 * m_count
                reasons.append(f"{m_count} misconception item(s) flagged (+{5 * m_count})")

            # Rule F: Bonus +15 if same misconception.linked_concept appears in >= 3 OTHER students
            # of same assessment (cross-student class-wide signal)
            resolved_concept = resolve_finding_field(finding, CorrectionFieldName.LINKED_CONCEPT)
            concepts_to_check = []
            if resolved_concept and str(resolved_concept).strip():
                concepts_to_check.append(str(resolved_concept).strip())
            if finding.misconceptions:
                for m in finding.misconceptions:
                    mc = m.get("linked_concept") if isinstance(m, dict) else getattr(m, "linked_concept", None)
                    if mc and str(mc).strip() and str(mc).strip() not in concepts_to_check:
                        concepts_to_check.append(str(mc).strip())

            class_wide_triggered = False
            for c_val in concepts_to_check:
                students_set = concept_students.get((a_id, c_val.lower()), set())
                other_students = students_set - {s_id}
                if len(other_students) >= 3:
                    score += 15
                    reasons.append(
                        f"Class-wide misconception: '{c_val}' shared with {len(other_students)} other students (+15)"
                    )
                    class_wide_triggered = True
                    break

            # Brief text resolution
            brief_text = (
                finding.evidence_excerpt
                or (
                    finding.misconceptions[0].get("evidence_excerpt")
                    if finding.misconceptions and isinstance(finding.misconceptions[0], dict)
                    else None
                )
                or finding.misconception_hypothesis
                or (finding.rationale[:120] if finding.rationale else "")
            )

            student_name = "Unknown Student"
            if student:
                student_name = student.full_name or student.email or f"Student #{student.id}"

            assessment_title = assessment.title if assessment else f"Assessment #{a_id}"

            items.append(
                PendingReviewItem(
                    finding_id=finding.id,
                    assessment_id=a_id,
                    assessment_title=assessment_title,
                    submission_id=submission.id if submission else 0,
                    student_id=s_id,
                    student_name=student_name,
                    question_id=q_id,
                    question_number=q_num,
                    question_prompt=question.prompt if question else None,
                    concept_name=finding.concept_name,
                    category=cat_str,
                    confidence=float(finding.confidence or 0.0),
                    requires_teacher_review=bool(req_review),
                    acknowledged_uncertainty=bool(finding.acknowledged_uncertainty),
                    review_status=str(finding.review_status),
                    teacher_corrected=bool(finding.teacher_corrected),
                    priority_score=score,
                    priority_reasons=reasons,
                    brief_text=brief_text,
                    misconceptions_count=m_count,
                    created_at=finding.created_at,
                )
            )

        # Sorting
        if sort == "priority":
            items.sort(key=lambda x: (-x.priority_score, x.created_at))
        else:
            items.sort(key=lambda x: x.created_at, reverse=True)

        total = len(items)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        paginated_items = items[(page - 1) * page_size : page * page_size]

        return PendingReviewQueueResponse(
            items=paginated_items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


review_queue_service = ReviewQueueService()

