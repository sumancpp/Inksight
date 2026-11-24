import hashlib
import time
from collections import defaultdict
from typing import Dict, List, Optional, Set
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models.assessment import Assessment
from app.models.enums import (
    CorrectionFieldName,
    FindingCategory,
    FindingReviewStatus,
)
from app.models.evaluation import EvaluationFinding, EvaluationRun
from app.models.submission import Submission
from app.schemas.cluster import MisconceptionClusterItem, MisconceptionClusterResponse
from app.services.correction_service import resolve_finding_field


class ClusterService:
    """
    Class-level misconception aggregation service.
    
    Note F Tradeoff:
    Clusters are computed from live data on every request with zero caching.
    Reason: Evaluation findings change in real-time via teacher reviews, acknowledgements,
    and field corrections. Cached clusters would present stale or invalidated findings to teachers.
    While live joins across evaluations, runs, and submissions have an O(N) complexity over findings,
    in practice (up to hundreds of student submissions per assessment), computation executes in <50ms.
    If assessments exceed thousands of submissions, asynchronous materialized rollup tables can be
    evaluated in a future optimization phase.
    """

    def get_misconception_clusters(
        self, db: Session, assessment_id: int
    ) -> MisconceptionClusterResponse:
        start_time = time.perf_counter()

        assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
        if not assessment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Assessment with id {assessment_id} not found.",
            )

        # Query all non-superseded findings for this assessment
        query = (
            db.query(EvaluationFinding)
            .join(EvaluationRun, EvaluationFinding.run_id == EvaluationRun.id)
            .join(Submission, EvaluationRun.submission_id == Submission.id)
            .filter(
                Submission.assessment_id == assessment_id,
                EvaluationFinding.review_status != FindingReviewStatus.SUPERSEDED.value,
            )
        )
        all_findings: List[EvaluationFinding] = query.all()

        total_findings_evaluated = len(all_findings)
        evaluated_student_ids: Set[int] = {
            f.run.submission.student_id
            for f in all_findings
            if f.run and f.run.submission
        }
        total_students_evaluated = len(evaluated_student_ids)

        # Filter strictly according to Note E:
        # 1. review_status MUST be 'accepted'
        # 2. Exclude requires_teacher_review == True AND NOT acknowledged_uncertainty
        # 3. Exclude correct-by-AI findings (only misconception/incorrect findings belong in clusters)
        valid_findings: List[EvaluationFinding] = []
        for f in all_findings:
            if not f.run or not f.run.submission:
                continue

            # Must be accepted
            if f.review_status != FindingReviewStatus.ACCEPTED.value:
                continue

            # Unacknowledged low confidence/review gate must be excluded
            req_review = resolve_finding_field(f, "requires_teacher_review")
            if req_review is None:
                req_review = f.requires_teacher_review
            if bool(req_review) and not bool(f.acknowledged_uncertainty):
                continue

            # Exclude correct-by-AI findings
            cat = resolve_finding_field(f, "category") or f.category
            cat_str = cat.value if hasattr(cat, "value") else str(cat)
            verdict = str(f.verdict or "").lower()
            if (
                cat_str.lower() in (FindingCategory.CORRECT_UNDERSTANDING.value, "correct_understanding")
                or verdict == "correct"
            ):
                continue

            valid_findings.append(f)

        # Group by resolved linked_concept (Feature 2 transitive resolver)
        grouped_data: Dict[str, Dict] = defaultdict(
            lambda: {
                "display_concept": "",
                "hypotheses": [],
                "student_ids": set(),
                "finding_ids": [],
                "evidence_excerpts": [],
                "severity_counts": {"low": 0, "medium": 0, "high": 0},
            }
        )

        for f in valid_findings:
            student_id = f.run.submission.student_id

            # Resolved concept via Feature 2 resolver
            raw_concept = resolve_finding_field(f, CorrectionFieldName.LINKED_CONCEPT)
            if not raw_concept and f.misconceptions:
                first = f.misconceptions[0]
                raw_concept = (
                    first.get("linked_concept")
                    if isinstance(first, dict)
                    else getattr(first, "linked_concept", None)
                )
            if not raw_concept:
                raw_concept = f.concept_name or "Unspecified Concept"

            concept_str = str(raw_concept).strip()
            concept_key = concept_str.lower()

            group = grouped_data[concept_key]
            if not group["display_concept"]:
                group["display_concept"] = concept_str

            group["student_ids"].add(student_id)
            group["finding_ids"].append(f.id)

            # Hypothesis
            raw_hypo = resolve_finding_field(f, CorrectionFieldName.MISCONCEPTION_HYPOTHESIS)
            if not raw_hypo and f.misconceptions:
                first = f.misconceptions[0]
                raw_hypo = (
                    first.get("hypothesis")
                    if isinstance(first, dict)
                    else getattr(first, "hypothesis", None)
                )
            if not raw_hypo:
                raw_hypo = f.misconception_hypothesis or f"Systematic error in {concept_str}"
            group["hypotheses"].append(str(raw_hypo).strip())

            # Evidence excerpt
            raw_excerpt = resolve_finding_field(f, CorrectionFieldName.EVIDENCE_EXCERPT)
            if not raw_excerpt and f.misconceptions:
                first = f.misconceptions[0]
                raw_excerpt = (
                    first.get("evidence_excerpt")
                    if isinstance(first, dict)
                    else getattr(first, "evidence_excerpt", None)
                )
            if not raw_excerpt:
                raw_excerpt = f.evidence_excerpt

            if raw_excerpt and str(raw_excerpt).strip():
                clean_exc = str(raw_excerpt).strip()
                if clean_exc not in group["evidence_excerpts"]:
                    group["evidence_excerpts"].append(clean_exc)

            # Severity
            raw_sev = resolve_finding_field(f, CorrectionFieldName.SEVERITY)
            if not raw_sev and f.misconceptions:
                first = f.misconceptions[0]
                raw_sev = (
                    first.get("severity")
                    if isinstance(first, dict)
                    else getattr(first, "severity", None)
                )
            sev_str = str(raw_sev or "medium").lower().strip()
            if sev_str not in ("low", "medium", "high"):
                sev_str = "medium"
            group["severity_counts"][sev_str] += 1

        clusters: List[MisconceptionClusterItem] = []
        isolated: List[MisconceptionClusterItem] = []

        for concept_key, group in grouped_data.items():
            distinct_students = sorted(list(group["student_ids"]))
            student_count = len(distinct_students)
            display_concept = group["display_concept"]

            # Representative hypothesis: most frequent or first
            representative_hypo = group["hypotheses"][0] if group["hypotheses"] else f"Misconception in {display_concept}"

            cluster_slug = hashlib.sha256(concept_key.encode("utf-8")).hexdigest()[:10]
            cluster_id = f"cluster-{cluster_slug}"

            top_excerpts = group["evidence_excerpts"][:3]

            if student_count >= 2:
                # Class-wide cluster (≥2 DISTINCT students)
                intervention = (
                    f"Targeted class review for '{display_concept}'. Direct intervention recommended across "
                    f"{student_count} students focusing on fundamental rules and counter-examples."
                )
                clusters.append(
                    MisconceptionClusterItem(
                        cluster_id=cluster_id,
                        linked_concept=display_concept,
                        hypothesis=representative_hypo,
                        student_count=student_count,
                        student_ids=distinct_students,
                        finding_ids=group["finding_ids"],
                        evidence_excerpts=top_excerpts,
                        severity_distribution=group["severity_counts"],
                        recommended_intervention=intervention,
                    )
                )
            else:
                # Isolated misconception (1 student)
                intervention = (
                    f"Individual targeted practice for '{display_concept}' assigned to Student #{distinct_students[0]}."
                )
                isolated.append(
                    MisconceptionClusterItem(
                        cluster_id=cluster_id,
                        linked_concept=display_concept,
                        hypothesis=representative_hypo,
                        student_count=student_count,
                        student_ids=distinct_students,
                        finding_ids=group["finding_ids"],
                        evidence_excerpts=top_excerpts,
                        severity_distribution=group["severity_counts"],
                        recommended_intervention=intervention,
                    )
                )

        # Sort clusters by student_count DESC, then finding_count DESC
        clusters.sort(key=lambda c: (-c.student_count, -len(c.finding_ids)))
        isolated.sort(key=lambda c: c.linked_concept.lower())

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Computed misconception clusters for assessment #{assessment_id} in {elapsed_ms:.2f}ms: "
            f"{len(clusters)} clusters, {len(isolated)} isolated."
        )

        return MisconceptionClusterResponse(
            assessment_id=assessment.id,
            assessment_title=assessment.title,
            clusters=clusters,
            isolated=isolated,
            total_findings_evaluated=total_findings_evaluated,
            total_students_evaluated=total_students_evaluated,
        )


cluster_service = ClusterService()

