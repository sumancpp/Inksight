from datetime import datetime
from typing import Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.assessment import Assessment
from app.models.enums import FindingReviewStatus, PracticeItemReviewStatus, UserRole
from app.models.evaluation import EvaluationFinding, EvaluationRun
from app.models.practice import PracticeResponse, PracticeSession
from app.models.remediation import RemediationItem, RemediationRun
from app.models.submission import Submission
from app.models.topic import LearningTopic
from app.models.user import User
from app.repositories.submission_repository import submission_repository
from app.schemas.outcome import (
    InterventionOutcomesSummary,
    StudentConceptProgressRead,
    StudentFollowupEvidenceRead,
    StudentProgressReportRead,
    TeacherFollowupEvidenceRead,
    TeacherInterventionOutcomeRead,
)


class OutcomeService:
    """
    Evidence-driven service for comparing diagnostic baselines with follow-up practice evidence,
    tracking intervention outcomes, and surfacing progress and actionable next steps.
    """

    def _assert_submission_access(self, submission: Submission, current_user: User) -> None:
        user_role = current_user.role.value if isinstance(current_user.role, UserRole) else str(current_user.role)
        if user_role == UserRole.STUDENT.value and submission.student_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this submission's progress report.",
            )

    def _evaluate_concept_outcome(
        self,
        concept_name: str,
        category: str,
        evidence_count: int,
        correct_count: int,
    ) -> tuple[str, str, str, str, str, str, str]:
        """
        Computes deterministic outcome status, uncertainty level, rationale, comparison, remaining gaps, and next steps.
        Enforces rule: Single response is insufficient to certify mastery.
        """
        if evidence_count == 0:
            outcome_status = "pending_followup"
            outcome_label = "Pending Follow-up"
            uncertainty_level = "High"
            uncertainty_rationale = (
                "No follow-up evidence collected yet. Initial misconception persists based on assessment baseline."
            )
            performance_comparison = (
                "Awaiting student practice. Baseline diagnostic gap remains unverified."
            )
            remaining_gaps = f"Needs practice on '{concept_name}' to address initial diagnostic gap ({category})."
            student_next_step = f"Start the assigned practice session to test and reinforce your understanding of {concept_name}."
            teacher_action = "Remind student to complete assigned practice session."
        elif evidence_count == 1:
            if correct_count == 1:
                outcome_status = "uncertain"
                outcome_label = "Tentative Progress (Single Response)"
                uncertainty_level = "Moderate-High"
                uncertainty_rationale = (
                    "Single correct response provides positive initial signal, but is insufficient to certify mastery without further verification."
                )
                performance_comparison = (
                    "1/1 correct (100%). Positive initial response compared to prior misconception, but confidence remains tentative."
                )
                remaining_gaps = "Additional follow-up evidence needed to verify consistent problem solving."
                student_next_step = "Complete at least 1 more follow-up question to solidify this concept."
                teacher_action = "Assign or review 1 additional verification item to confirm conceptual stability."
            else:
                outcome_status = "persisting_gap"
                outcome_label = "Persisting Gap (Needs Support)"
                uncertainty_level = "Moderate"
                uncertainty_rationale = (
                    "Follow-up attempt was incorrect; initial misconception was not resolved by the initial practice item."
                )
                performance_comparison = (
                    "0/1 correct (0%). Misconception persists; student gave incorrect follow-up response."
                )
                remaining_gaps = f"Misconception regarding '{concept_name}' is still evident in follow-up exercise."
                student_next_step = "Review the concept notes and discuss with your teacher before trying another question."
                teacher_action = "Schedule a targeted 1-on-1 review or provide alternative instructional explanation."
        else:
            # evidence_count >= 2
            acc = (float(correct_count) / float(evidence_count)) * 100.0
            if correct_count == evidence_count:
                outcome_status = "improved"
                outcome_label = "Demonstrated Improvement"
                uncertainty_level = "Low-Moderate"
                uncertainty_rationale = (
                    f"Consistent success across {evidence_count} follow-up items reduces diagnostic uncertainty. Formative monitoring continues."
                )
                performance_comparison = (
                    f"Improved from prior misconception: {correct_count}/{evidence_count} correct (100%) across follow-up assessments."
                )
                remaining_gaps = "None detected in follow-up practice; reinforce in cumulative reviews."
                student_next_step = "Great progress! You have demonstrated consistent understanding. Move on to next topic."
                teacher_action = "Intervention successful; reinforce during standard formative reviews."
            elif correct_count == 0:
                outcome_status = "persisting_gap"
                outcome_label = "Persisting Misconception"
                uncertainty_level = "Low"
                uncertainty_rationale = (
                    f"Consistent errors across {evidence_count} attempts confirm that initial misconception persists."
                )
                performance_comparison = (
                    f"Persistent gap: 0/{evidence_count} correct (0%). Prior misconception remains unaddressed."
                )
                remaining_gaps = f"Fundamental misunderstanding of '{concept_name}' remains after {evidence_count} follow-up attempts."
                student_next_step = "Seek direct assistance from your teacher before attempting more questions."
                teacher_action = "Intervene directly with alternative, scaffolded instructional material."
            else:
                outcome_status = "uncertain"
                outcome_label = "Mixed Evidence / Partial Progress"
                uncertainty_level = "High"
                uncertainty_rationale = (
                    f"Inconsistent performance ({correct_count}/{evidence_count} correct, {acc:.0f}%) indicates partial conceptual understanding."
                )
                performance_comparison = (
                    f"Partial progress: {correct_count}/{evidence_count} correct ({acc:.0f}%). Mixed signals compared to baseline."
                )
                remaining_gaps = f"Inconsistent application of '{concept_name}'. Specific edge cases or steps cause confusion."
                student_next_step = "Practice 1-2 more problems focusing on the specific steps you found challenging."
                teacher_action = "Inspect student practice response details to pinpoint the specific stumbling block."

        return (
            outcome_status,
            outcome_label,
            uncertainty_level,
            uncertainty_rationale,
            performance_comparison,
            remaining_gaps,
            student_next_step if student_next_step else teacher_action,
        )

    def get_submission_intervention_outcomes(
        self, db: Session, submission_id: int
    ) -> InterventionOutcomesSummary:
        """
        Compiles teacher-facing intervention outcomes for a submission.
        Connects diagnostic findings, approved remediation items, and completed practice responses.
        """
        submission = submission_repository.get_by_id(db=db, submission_id=submission_id)
        if not submission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission with id {submission_id} not found.",
            )

        student = db.query(User).filter(User.id == submission.student_id).first()
        student_name = student.full_name if student else f"Student #{submission.student_id}"

        # Fetch accepted findings for this submission
        findings = (
            db.query(EvaluationFinding)
            .join(EvaluationRun, EvaluationFinding.run_id == EvaluationRun.id)
            .filter(
                EvaluationRun.submission_id == submission_id,
                EvaluationFinding.review_status == FindingReviewStatus.ACCEPTED.value,
            )
            .order_by(EvaluationFinding.id.asc())
            .all()
        )

        outcomes: List[TeacherInterventionOutcomeRead] = []

        for finding in findings:
            eval_run = db.query(EvaluationRun).filter(EvaluationRun.id == finding.run_id).first()
            question_id = eval_run.question_id if eval_run else 0
            topic = db.query(LearningTopic).filter(LearningTopic.id == finding.topic_id).first() if finding.topic_id else None
            topic_name = topic.name if topic else (finding.concept_name or "General Topic")
            concept_name = finding.concept_name or topic_name

            # Approved remediation items
            items = (
                db.query(RemediationItem)
                .filter(
                    RemediationItem.finding_id == finding.id,
                    RemediationItem.review_status.in_([
                        PracticeItemReviewStatus.APPROVED.value,
                        PracticeItemReviewStatus.EDITED.value,
                    ]),
                )
                .order_by(RemediationItem.id.asc())
                .all()
            )

            support_summary = (
                f"Delivered {len(items)} teacher-approved practice item(s)"
                if items
                else "No approved practice items yet."
            )

            # Query follow-up practice responses for this finding
            responses = (
                db.query(PracticeResponse)
                .filter(PracticeResponse.finding_id == finding.id)
                .order_by(PracticeResponse.submitted_at.asc())
                .all()
            )

            evidence_count = len(responses)
            correct_count = sum(1 for r in responses if r.is_correct)
            accuracy = (float(correct_count) / float(evidence_count) * 100.0) if evidence_count > 0 else 0.0
            latest_at = max((r.submitted_at for r in responses), default=None)

            # Build follow-up evidence items with provenance
            followup_evs: List[TeacherFollowupEvidenceRead] = []
            for r in responses:
                ritem = db.query(RemediationItem).filter(RemediationItem.id == r.remediation_item_id).first()
                q_text = ritem.edited_question_text or ritem.question_text if ritem else "Practice Item"
                q_type = ritem.question_type if ritem else "short_answer"
                q_diff = ritem.difficulty if ritem else "medium"
                followup_evs.append(
                    TeacherFollowupEvidenceRead(
                        response_id=r.id,
                        session_id=r.session_id,
                        remediation_item_id=r.remediation_item_id,
                        item_question_text=q_text,
                        item_question_type=q_type,
                        difficulty=q_diff,
                        student_answer=r.student_answer,
                        is_correct=r.is_correct,
                        score=r.score,
                        feedback=r.feedback,
                        submitted_at=r.submitted_at,
                    )
                )

            followup_summary = (
                f"{correct_count} of {evidence_count} follow-up question(s) answered correctly ({accuracy:.0f}%)."
                if evidence_count > 0
                else "No follow-up practice responses recorded yet."
            )

            (
                outcome_status,
                outcome_label,
                uncertainty_level,
                uncertainty_rationale,
                performance_comparison,
                remaining_gaps,
                recommended_action,
            ) = self._evaluate_concept_outcome(
                concept_name=concept_name,
                category=finding.category,
                evidence_count=evidence_count,
                correct_count=correct_count,
            )

            outcomes.append(
                TeacherInterventionOutcomeRead(
                    finding_id=finding.id,
                    run_id=finding.run_id,
                    question_id=question_id,
                    topic_id=finding.topic_id,
                    topic_name=topic_name,
                    concept_name=concept_name,
                    student_id=submission.student_id,
                    student_name=student_name,
                    submission_id=submission.id,
                    prior_category=finding.category,
                    prior_confidence=finding.confidence,
                    prior_evidence_excerpt=finding.evidence_excerpt,
                    prior_rationale=finding.rationale,
                    prior_uncertainty=finding.uncertainty_rationale,
                    finding_review_status=finding.review_status,
                    finding_review_notes=finding.review_notes,
                    remediation_items_count=len(items),
                    support_summary=support_summary,
                    evidence_count=evidence_count,
                    correct_count=correct_count,
                    accuracy_percentage=round(accuracy, 1),
                    latest_response_at=latest_at,
                    followup_summary=followup_summary,
                    followup_responses=followup_evs,
                    outcome_status=outcome_status,
                    outcome_label=outcome_label,
                    uncertainty_level=uncertainty_level,
                    uncertainty_rationale=uncertainty_rationale,
                    performance_comparison=performance_comparison,
                    recommended_action=recommended_action,
                )
            )

        improved = sum(1 for o in outcomes if o.outcome_status == "improved")
        uncertain = sum(1 for o in outcomes if o.outcome_status == "uncertain")
        persisting = sum(1 for o in outcomes if o.outcome_status == "persisting_gap")
        pending = sum(1 for o in outcomes if o.outcome_status == "pending_followup")

        return InterventionOutcomesSummary(
            submission_id=submission.id,
            assessment_id=submission.assessment_id,
            total_interventions=len(outcomes),
            improved_count=improved,
            uncertain_count=uncertain,
            persisting_gap_count=persisting,
            pending_count=pending,
            outcomes=outcomes,
        )

    def get_assessment_intervention_outcomes(
        self, db: Session, assessment_id: int
    ) -> InterventionOutcomesSummary:
        """Compiles intervention outcomes aggregated across all submissions for an assessment."""
        assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
        if not assessment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Assessment with id {assessment_id} not found.",
            )

        submissions = (
            db.query(Submission)
            .filter(Submission.assessment_id == assessment_id)
            .order_by(Submission.id.asc())
            .all()
        )

        all_outcomes: List[TeacherInterventionOutcomeRead] = []
        for sub in submissions:
            sub_summary = self.get_submission_intervention_outcomes(db=db, submission_id=sub.id)
            all_outcomes.extend(sub_summary.outcomes)

        improved = sum(1 for o in all_outcomes if o.outcome_status == "improved")
        uncertain = sum(1 for o in all_outcomes if o.outcome_status == "uncertain")
        persisting = sum(1 for o in all_outcomes if o.outcome_status == "persisting_gap")
        pending = sum(1 for o in all_outcomes if o.outcome_status == "pending_followup")

        return InterventionOutcomesSummary(
            assessment_id=assessment_id,
            total_interventions=len(all_outcomes),
            improved_count=improved,
            uncertain_count=uncertain,
            persisting_gap_count=persisting,
            pending_count=pending,
            outcomes=all_outcomes,
        )

    def get_student_progress_report(
        self, db: Session, submission_id: int, current_user: User
    ) -> StudentProgressReportRead:
        """
        Compiles student-facing learning loop progress and follow-up outcome report.
        STRICT PRIVACY GUARANTEE: Never exposes teacher answer keys, teacher rationales,
        or internal review comments.
        """
        submission = submission_repository.get_by_id(db=db, submission_id=submission_id)
        if not submission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission with id {submission_id} not found.",
            )

        self._assert_submission_access(submission, current_user)

        assessment = db.query(Assessment).filter(Assessment.id == submission.assessment_id).first()
        assessment_title = assessment.title if assessment else f"Assessment #{submission.assessment_id}"

        findings = (
            db.query(EvaluationFinding)
            .join(EvaluationRun, EvaluationFinding.run_id == EvaluationRun.id)
            .filter(
                EvaluationRun.submission_id == submission_id,
                EvaluationFinding.review_status == FindingReviewStatus.ACCEPTED.value,
            )
            .order_by(EvaluationFinding.id.asc())
            .all()
        )

        concepts: List[StudentConceptProgressRead] = []

        for finding in findings:
            topic = db.query(LearningTopic).filter(LearningTopic.id == finding.topic_id).first() if finding.topic_id else None
            topic_name = topic.name if topic else (finding.concept_name or "General Topic")
            concept_name = finding.concept_name or topic_name

            # Student-safe baseline description
            baseline_gap = f"Initial diagnostic assessment indicated an area for improvement: {finding.category.replace('_', ' ').capitalize()}."

            responses = (
                db.query(PracticeResponse)
                .filter(PracticeResponse.finding_id == finding.id)
                .order_by(PracticeResponse.submitted_at.asc())
                .all()
            )

            evidence_count = len(responses)
            correct_count = sum(1 for r in responses if r.is_correct)
            accuracy = (float(correct_count) / float(evidence_count) * 100.0) if evidence_count > 0 else 0.0

            followup_evs: List[StudentFollowupEvidenceRead] = []
            for r in responses:
                ritem = db.query(RemediationItem).filter(RemediationItem.id == r.remediation_item_id).first()
                q_type = ritem.question_type if ritem else "short_answer"
                followup_evs.append(
                    StudentFollowupEvidenceRead(
                        item_id=r.remediation_item_id,
                        question_type=q_type,
                        student_answer=r.student_answer,
                        is_correct=r.is_correct,
                        score=r.score,
                        feedback=r.feedback,
                        submitted_at=r.submitted_at,
                    )
                )

            (
                outcome_status,
                outcome_label,
                uncertainty_level,
                uncertainty_rationale,
                performance_comparison,
                remaining_gaps,
                student_next_step,
            ) = self._evaluate_concept_outcome(
                concept_name=concept_name,
                category=finding.category,
                evidence_count=evidence_count,
                correct_count=correct_count,
            )

            concepts.append(
                StudentConceptProgressRead(
                    topic_id=finding.topic_id,
                    topic_name=topic_name,
                    concept_name=concept_name,
                    baseline_diagnostic_gap=baseline_gap,
                    baseline_evidence_excerpt=finding.evidence_excerpt,
                    evidence_count=evidence_count,
                    correct_count=correct_count,
                    accuracy_percentage=round(accuracy, 1),
                    outcome_status=outcome_status,
                    status_label=outcome_label,
                    uncertainty_level=uncertainty_level,
                    uncertainty_rationale=uncertainty_rationale,
                    remaining_gaps=remaining_gaps,
                    recommended_next_step=student_next_step,
                    followup_responses=followup_evs,
                )
            )

        improved = sum(1 for c in concepts if c.outcome_status == "improved")
        uncertain = sum(1 for c in concepts if c.outcome_status == "uncertain")
        persisting = sum(1 for c in concepts if c.outcome_status == "persisting_gap")
        pending = sum(1 for c in concepts if c.outcome_status == "pending_followup")

        if persisting > 0:
            overall_next = f"Prioritize reviewing {persisting} concept area(s) showing persistent gaps before advancing."
        elif uncertain > 0:
            overall_next = f"Complete additional practice problems on {uncertain} concept area(s) to confirm consistent progress."
        elif improved > 0 and pending == 0:
            overall_next = "Outstanding effort! All evaluated areas show positive follow-up improvement."
        else:
            overall_next = "Complete assigned follow-up practice exercises to update your concept progress."

        return StudentProgressReportRead(
            submission_id=submission.id,
            assessment_id=submission.assessment_id,
            assessment_title=assessment_title,
            total_concepts_tracked=len(concepts),
            improved_count=improved,
            uncertain_count=uncertain,
            persisting_gap_count=persisting,
            pending_count=pending,
            concepts=concepts,
            overall_next_step=overall_next,
        )


outcome_service = OutcomeService()

