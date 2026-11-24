from datetime import datetime, timezone
from typing import Any, List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models.enums import CorrectionFieldName, CorrectionStatus
from app.models.evaluation import EvaluationFinding, FindingReviewAudit
from app.models.correction import FindingCorrection
from app.schemas.evaluation import compute_confidence_level


def resolve_finding_field(finding: EvaluationFinding, field_name: str | CorrectionFieldName) -> Any:
    """
    Downstream read rule: any consumer of misconception fields must read through
    resolve_finding_field(finding, field) that returns active correction if present, else original.
    """
    f_str = field_name.value if isinstance(field_name, CorrectionFieldName) else str(field_name)

    # Check active correction on finding
    if hasattr(finding, "corrections") and finding.corrections:
        for corr in finding.corrections:
            if corr.field_name == f_str and corr.status == CorrectionStatus.ACTIVE.value:
                return corr.corrected_value

    # Default fallback to finding model fields
    if f_str == CorrectionFieldName.MISCONCEPTION_HYPOTHESIS.value:
        return finding.misconception_hypothesis
    elif f_str == CorrectionFieldName.EVIDENCE_EXCERPT.value:
        if finding.evidence_excerpt:
            return finding.evidence_excerpt
        if finding.misconceptions and len(finding.misconceptions) > 0:
            first = finding.misconceptions[0]
            val = first.get("evidence_excerpt") if isinstance(first, dict) else getattr(first, "evidence_excerpt", None)
            if val:
                return val
        return None
    elif f_str == CorrectionFieldName.LINKED_CONCEPT.value:
        if finding.misconceptions and len(finding.misconceptions) > 0:
            first = finding.misconceptions[0]
            val = first.get("linked_concept") if isinstance(first, dict) else getattr(first, "linked_concept", None)
            if val:
                return val
        return finding.concept_name
    elif f_str == CorrectionFieldName.SEVERITY.value:
        if finding.misconceptions and len(finding.misconceptions) > 0:
            first = finding.misconceptions[0]
            return first.get("severity") if isinstance(first, dict) else getattr(first, "severity", None)
        return None
    elif f_str == CorrectionFieldName.CONFIDENCE_SCORE.value:
        return finding.confidence

    return getattr(finding, f_str, None)


class CorrectionService:
    def get_corrections_for_finding(self, db: Session, finding_id: int) -> List[FindingCorrection]:
        return (
            db.query(FindingCorrection)
            .filter(FindingCorrection.finding_id == finding_id)
            .order_by(FindingCorrection.id.desc())
            .all()
        )

    def apply_correction(
        self,
        db: Session,
        finding_id: int,
        field_name: CorrectionFieldName | str,
        new_value: Any,
        reason: str,
        teacher_id: int,
    ) -> FindingCorrection:
        finding = db.query(EvaluationFinding).filter(EvaluationFinding.id == finding_id).first()
        if not finding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation finding with id {finding_id} not found.",
            )

        if not reason or not reason.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A non-empty correction reason is required.",
            )

        try:
            field_enum = CorrectionFieldName(field_name)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid correction field name: '{field_name}'. Must be one of {[e.value for e in CorrectionFieldName]}.",
            )

        # Value validation
        if field_enum == CorrectionFieldName.CONFIDENCE_SCORE:
            try:
                score_val = float(new_value)
                if not (0.0 <= score_val <= 1.0):
                    raise ValueError()
                new_value = score_val
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="confidence_score must be a float between 0.0 and 1.0.",
                )
        elif field_enum == CorrectionFieldName.SEVERITY:
            if new_value not in ("low", "medium", "high"):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="severity must be 'low', 'medium', or 'high'.",
                )
        else:
            if not str(new_value).strip():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"{field_enum.value} must not be empty.",
                )

        # Determine original AI value
        original_value = resolve_finding_field(finding, field_enum)

        # Mark prior ACTIVE correction for same field as REVERTED
        prior_active = (
            db.query(FindingCorrection)
            .filter(
                FindingCorrection.finding_id == finding_id,
                FindingCorrection.field_name == field_enum.value,
                FindingCorrection.status == CorrectionStatus.ACTIVE.value,
            )
            .all()
        )
        for pa in prior_active:
            pa.status = CorrectionStatus.REVERTED.value

        # Create new ACTIVE correction
        correction = FindingCorrection(
            finding_id=finding.id,
            field_name=field_enum.value,
            original_value=original_value,
            corrected_value=new_value,
            corrected_by=teacher_id,
            correction_reason=reason.strip(),
            status=CorrectionStatus.ACTIVE.value,
            corrected_at=datetime.now(timezone.utc),
        )
        db.add(correction)

        # Recompute derived finding fields
        if field_enum == CorrectionFieldName.CONFIDENCE_SCORE:
            new_score = float(new_value)
            finding.confidence = new_score
            derived_level = compute_confidence_level(new_score)
            if finding.confidence_details is None:
                finding.confidence_details = {
                    "score": new_score,
                    "level": derived_level,
                    "uncertainty_reasons": ["teacher_corrected_confidence"],
                }
            else:
                conf = (
                    dict(finding.confidence_details)
                    if isinstance(finding.confidence_details, dict)
                    else finding.confidence_details.model_dump()
                )
                conf["score"] = new_score
                conf["level"] = derived_level
                finding.confidence_details = conf

            # Note B: If level transitions low->high, do NOT auto-clear requires_teacher_review.
            # requires_teacher_review stays True UNTIL teacher explicitly re-reviews.
            if derived_level == "low":
                finding.requires_teacher_review = True
            elif finding.requires_teacher_review:
                finding.requires_teacher_review = True

        elif field_enum == CorrectionFieldName.MISCONCEPTION_HYPOTHESIS:
            finding.misconception_hypothesis = str(new_value)
            if finding.misconceptions and len(finding.misconceptions) > 0:
                first = (
                    dict(finding.misconceptions[0])
                    if isinstance(finding.misconceptions[0], dict)
                    else finding.misconceptions[0].model_dump()
                )
                first["hypothesis"] = str(new_value)
                finding.misconceptions = [first] + finding.misconceptions[1:]

        elif field_enum == CorrectionFieldName.LINKED_CONCEPT:
            if finding.misconceptions and len(finding.misconceptions) > 0:
                first = (
                    dict(finding.misconceptions[0])
                    if isinstance(finding.misconceptions[0], dict)
                    else finding.misconceptions[0].model_dump()
                )
                first["linked_concept"] = str(new_value)
                finding.misconceptions = [first] + finding.misconceptions[1:]

        elif field_enum == CorrectionFieldName.EVIDENCE_EXCERPT:
            finding.evidence_excerpt = str(new_value)
            if finding.misconceptions and len(finding.misconceptions) > 0:
                first = (
                    dict(finding.misconceptions[0])
                    if isinstance(finding.misconceptions[0], dict)
                    else finding.misconceptions[0].model_dump()
                )
                first["evidence_excerpt"] = str(new_value)
                finding.misconceptions = [first] + finding.misconceptions[1:]

        elif field_enum == CorrectionFieldName.SEVERITY:
            if finding.misconceptions and len(finding.misconceptions) > 0:
                first = (
                    dict(finding.misconceptions[0])
                    if isinstance(finding.misconceptions[0], dict)
                    else finding.misconceptions[0].model_dump()
                )
                first["severity"] = str(new_value)
                finding.misconceptions = [first] + finding.misconceptions[1:]

        # Log FindingReviewAudit row
        audit = FindingReviewAudit(
            finding_id=finding.id,
            reviewer_id=teacher_id,
            action="corrected",
            review_notes=f"Corrected {field_enum.value}: '{original_value}' -> '{new_value}'. Reason: {reason}",
            acknowledged_uncertainty=finding.acknowledged_uncertainty,
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit)
        db.commit()
        db.refresh(correction)
        db.refresh(finding)
        return correction

    def revert_to_ai(
        self,
        db: Session,
        finding_id: int,
        correction_id: int,
        teacher_id: int,
    ) -> FindingCorrection:
        finding = db.query(EvaluationFinding).filter(EvaluationFinding.id == finding_id).first()
        if not finding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation finding with id {finding_id} not found.",
            )

        correction = (
            db.query(FindingCorrection)
            .filter(FindingCorrection.id == correction_id, FindingCorrection.finding_id == finding_id)
            .first()
        )
        if not correction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Correction with id {correction_id} not found on finding {finding_id}.",
            )

        correction.status = CorrectionStatus.REVERTED.value

        # Revert finding field to original_value
        field_name = correction.field_name
        orig = correction.original_value

        if field_name == CorrectionFieldName.CONFIDENCE_SCORE.value and orig is not None:
            finding.confidence = float(orig)
            derived_level = compute_confidence_level(float(orig))
            if finding.confidence_details:
                conf = (
                    dict(finding.confidence_details)
                    if isinstance(finding.confidence_details, dict)
                    else finding.confidence_details.model_dump()
                )
                conf["score"] = float(orig)
                conf["level"] = derived_level
                finding.confidence_details = conf
            finding.requires_teacher_review = (derived_level == "low")
        elif field_name == CorrectionFieldName.MISCONCEPTION_HYPOTHESIS.value and orig is not None:
            finding.misconception_hypothesis = str(orig)
            if finding.misconceptions and len(finding.misconceptions) > 0:
                first = (
                    dict(finding.misconceptions[0])
                    if isinstance(finding.misconceptions[0], dict)
                    else finding.misconceptions[0].model_dump()
                )
                first["hypothesis"] = str(orig)
                finding.misconceptions = [first] + finding.misconceptions[1:]
        elif field_name == CorrectionFieldName.LINKED_CONCEPT.value and orig is not None:
            if finding.misconceptions and len(finding.misconceptions) > 0:
                first = (
                    dict(finding.misconceptions[0])
                    if isinstance(finding.misconceptions[0], dict)
                    else finding.misconceptions[0].model_dump()
                )
                first["linked_concept"] = str(orig)
                finding.misconceptions = [first] + finding.misconceptions[1:]
        elif field_name == CorrectionFieldName.EVIDENCE_EXCERPT.value and orig is not None:
            finding.evidence_excerpt = str(orig)
            if finding.misconceptions and len(finding.misconceptions) > 0:
                first = (
                    dict(finding.misconceptions[0])
                    if isinstance(finding.misconceptions[0], dict)
                    else finding.misconceptions[0].model_dump()
                )
                first["evidence_excerpt"] = str(orig)
                finding.misconceptions = [first] + finding.misconceptions[1:]
        elif field_name == CorrectionFieldName.SEVERITY.value:
            if finding.misconceptions and len(finding.misconceptions) > 0:
                first = (
                    dict(finding.misconceptions[0])
                    if isinstance(finding.misconceptions[0], dict)
                    else finding.misconceptions[0].model_dump()
                )
                first["severity"] = str(orig) if orig is not None else None
                finding.misconceptions = [first] + finding.misconceptions[1:]

        audit = FindingReviewAudit(
            finding_id=finding.id,
            reviewer_id=teacher_id,
            action="reverted_correction",
            review_notes=f"Reverted {field_name} correction back to original AI value: '{orig}'",
            acknowledged_uncertainty=finding.acknowledged_uncertainty,
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit)
        db.commit()
        db.refresh(correction)
        db.refresh(finding)
        return correction


correction_service = CorrectionService()
