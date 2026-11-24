from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models.enums import CorrectionFieldName, FindingReviewStatus, FollowUpQuestionType, FollowUpStatus
from app.models.evaluation import EvaluationFinding
from app.models.follow_up import FollowUpQuestion
from app.schemas.follow_up import (
    FollowUpGenerationInput,
    FollowUpQuestionPayload,
    FollowUpRubric,
    RubricCriterion,
)
from app.services.correction_service import resolve_finding_field
from app.services.evaluator.factory import get_evaluator


class FollowUpGenerationService:
    async def propose_follow_up(
        self,
        db: Session,
        finding_id: int,
        teacher_id: int,
    ) -> FollowUpQuestion:
        finding = (
            db.query(EvaluationFinding)
            .filter(EvaluationFinding.id == finding_id)
            .first()
        )
        if not finding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation finding with id {finding_id} not found.",
            )

        # Guard: refuse if finding.review_status not in (accepted)
        if finding.review_status != FindingReviewStatus.ACCEPTED.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot generate follow-up question for finding with review status '{finding.review_status}'. Finding must be accepted by a teacher first.",
            )

        # Guard: refuse if requires_teacher_review == True AND acknowledged_uncertainty == False
        if finding.requires_teacher_review and not finding.acknowledged_uncertainty:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot generate follow-up question for low-confidence finding without teacher review and acknowledged uncertainty.",
            )

        # Guard: must have >= 1 grounded misconception
        misconceptions = finding.misconceptions or []
        if not misconceptions and not finding.misconception_hypothesis:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Finding has no grounded misconception hypotheses to verify.",
            )

        if misconceptions and len(misconceptions) > 0:
            first_m = misconceptions[0]
            if isinstance(first_m, dict):
                hypothesis = first_m.get("hypothesis", "")
                linked_concept = first_m.get("linked_concept", "")
                evidence_excerpt = first_m.get("evidence_excerpt", "")
            else:
                hypothesis = getattr(first_m, "hypothesis", "")
                linked_concept = getattr(first_m, "linked_concept", "")
                evidence_excerpt = getattr(first_m, "evidence_excerpt", "")
        else:
            hypothesis = finding.misconception_hypothesis or ""
            linked_concept = finding.concept_name or "Assessment Concept"
            evidence_excerpt = finding.evidence_excerpt or ""

        # Note A: Downstream consumer must read active corrections via resolve_finding_field
        resolved_hyp = resolve_finding_field(finding, CorrectionFieldName.MISCONCEPTION_HYPOTHESIS)
        resolved_concept = resolve_finding_field(finding, CorrectionFieldName.LINKED_CONCEPT)
        resolved_evidence = resolve_finding_field(finding, CorrectionFieldName.EVIDENCE_EXCERPT)

        hypothesis = resolved_hyp if resolved_hyp is not None else hypothesis
        linked_concept = resolved_concept if resolved_concept is not None else linked_concept
        evidence_excerpt = resolved_evidence if resolved_evidence is not None else evidence_excerpt

        # Consistency check between linked_concept and hypothesis
        if linked_concept and hypothesis:
            lc_norm = linked_concept.strip().lower()
            hyp_norm = hypothesis.strip().lower()
            if lc_norm not in hyp_norm and hyp_norm not in lc_norm:
                logger.warning(
                    f"FollowUpGenerationService: Misconception linked_concept '{linked_concept}' and "
                    f"hypothesis '{hypothesis}' do not overlap. Prioritizing linked_concept as canonical target."
                )

        # Retrieve assessment and question context
        question = finding.run.question if finding.run else None
        if not question:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not determine question and assessment context for finding.",
            )

        assessment_id = question.assessment_id
        question_prompt = question.prompt
        student_answer = (
            finding.run.question_answer.answer_text
            if finding.run and finding.run.question_answer
            else (finding.run.answer_text_snapshot if finding.run else "")
        )

        input_payload = FollowUpGenerationInput(
            finding_id=finding.id,
            question_prompt=question_prompt,
            student_answer=student_answer or "",
            misconception_hypothesis=hypothesis,
            linked_concept=linked_concept,
            evidence_excerpt=evidence_excerpt,
        )

        evaluator = get_evaluator()
        try:
            generated: FollowUpQuestionPayload = await evaluator.generate_follow_up(input_payload)
        except Exception as exc:
            logger.error(f"FollowUpGenerationService: Generation failed: {exc}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Follow-up generation failed: {str(exc)}",
            )

        # Grounding check: question MUST reference concept from misconception.linked_concept OR linked_concept in misconception_hypothesis
        target_concepts = [c.lower() for c in [linked_concept, hypothesis] if c]
        gen_concept = (generated.concept or "").lower()
        question_text_lower = (generated.question_text or "").lower()

        concept_grounded = any(tc in gen_concept or gen_concept in tc for tc in target_concepts if tc)
        question_grounded = gen_concept in question_text_lower or any(tc in question_text_lower for tc in target_concepts if tc)

        if not (concept_grounded and question_grounded):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Generated follow-up failed grounding: concept '{generated.concept}' does not "
                    f"reference target concept '{linked_concept}' or hypothesis."
                ),
            )

        rubric_dict = generated.rubric.model_dump()
        total_marks = sum(c.get("marks", 0.0) for c in rubric_dict.get("criteria", []))
        if total_marks <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Follow-up question rubric total marks must be greater than 0.",
            )

        # Persist as PROPOSED. Never auto-approve.
        follow_up = FollowUpQuestion(
            finding_id=finding.id,
            assessment_id=assessment_id,
            concept=generated.concept,
            question_text=generated.question_text,
            expected_answer=generated.expected_answer,
            rubric=rubric_dict,
            question_type=(
                generated.question_type.value
                if hasattr(generated.question_type, "value")
                else str(generated.question_type)
            ),
            status=FollowUpStatus.PROPOSED.value,
            proposed_by="system",
            created_at=datetime.now(timezone.utc),
        )
        db.add(follow_up)
        db.commit()
        db.refresh(follow_up)
        return follow_up

    def approve_follow_up(
        self,
        db: Session,
        follow_up_id: int,
        teacher_id: int,
        audit_notes: Optional[str] = None,
    ) -> FollowUpQuestion:
        follow_up = (
            db.query(FollowUpQuestion)
            .filter(FollowUpQuestion.id == follow_up_id)
            .first()
        )
        if not follow_up:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Follow-up question with id {follow_up_id} not found.",
            )

        follow_up.status = FollowUpStatus.APPROVED.value
        follow_up.approved_by = teacher_id
        follow_up.approved_at = datetime.now(timezone.utc)
        if audit_notes:
            follow_up.audit_notes = (
                f"{follow_up.audit_notes}\n{audit_notes}".strip()
                if follow_up.audit_notes
                else audit_notes
            )
        db.commit()
        db.refresh(follow_up)
        return follow_up

    def reject_follow_up(
        self,
        db: Session,
        follow_up_id: int,
        teacher_id: int,
        reason: str,
    ) -> FollowUpQuestion:
        follow_up = (
            db.query(FollowUpQuestion)
            .filter(FollowUpQuestion.id == follow_up_id)
            .first()
        )
        if not follow_up:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Follow-up question with id {follow_up_id} not found.",
            )

        follow_up.status = FollowUpStatus.REJECTED.value
        reject_note = f"Rejected by teacher {teacher_id}: {reason}"
        follow_up.audit_notes = (
            f"{follow_up.audit_notes}\n{reject_note}".strip()
            if follow_up.audit_notes
            else reject_note
        )
        db.commit()
        db.refresh(follow_up)
        return follow_up

    def get_follow_ups_for_finding(
        self,
        db: Session,
        finding_id: int,
    ) -> List[FollowUpQuestion]:
        return (
            db.query(FollowUpQuestion)
            .filter(FollowUpQuestion.finding_id == finding_id)
            .order_by(FollowUpQuestion.id.desc())
            .all()
        )


followup_generation_service = FollowUpGenerationService()

