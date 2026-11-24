import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Ensure backend root is on sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.logging import logger
from app.core.security import hash_password
from app.models.assessment import Assessment, Question
from app.models.enums import (
    FindingCategory,
    FindingReviewStatus,
    QuestionType,
    SubmissionStatus,
    UploadStatus,
    UserRole,
)
from app.models.evaluation import EvaluationFinding, EvaluationRun
from app.models.matching import ProposedAnswer
from app.models.ocr import OCRExtraction
from app.models.submission import AnswerSheetUpload, QuestionAnswer, Submission
from app.models.topic import LearningTopic
from app.models.user import User


def seed_cluster_demo(
    db: Session,
    assessment_id: Optional[int] = None,
    force: bool = False,
    dry_run: bool = False,
) -> Assessment:
    """
    Management script for Note D: seeds real, non-fabricated demo assessment data with
    2 distinct misconception clusters (2 students each):
    1. 'Fraction Division' (2 distinct students)
    2. 'Reverse Percentage' (2 distinct students)

    Production Safety:
    - If target assessment already has existing findings > 0, requires `force=True` (otherwise refuses).
    - If `dry_run=True`, prints planned entities without writing/committing to the database.
    - If `assessment_id` is omitted, defaults to creating a NEW assessment named "Cluster Demo (Seeded YYYY-MM-DD)".
    """
    # 1. Ensure Demo Teachers
    # Note: Seeded demo teachers smith@learngraph.edu and smith@inksight.edu (password: teacher123) are required for DemoAuthGate auto-login
    smith = (
        db.query(User)
        .filter(User.email == "smith@learngraph.edu")
        .first()
    )
    if not smith and not dry_run:
        smith = User(
            email="smith@learngraph.edu",
            full_name="Dr. Smith",
            hashed_password=hash_password("teacher123"),
            role=UserRole.TEACHER.value,
            is_active=True,
        )
        db.add(smith)
        db.commit()
        db.refresh(smith)

    smith_inksight = (
        db.query(User)
        .filter(User.email == "smith@inksight.edu")
        .first()
    )
    if not smith_inksight and not dry_run:
        smith_inksight = User(
            email="smith@inksight.edu",
            full_name="Dr. Smith",
            hashed_password=hash_password("teacher123"),
            role=UserRole.TEACHER.value,
            is_active=True,
        )
        db.add(smith_inksight)
        db.commit()
        db.refresh(smith_inksight)

    teacher = (
        db.query(User)
        .filter(User.email == "demo_teacher_cluster@learngraph.internal")
        .first()
    )
    if not teacher and not dry_run:
        teacher = User(
            email="demo_teacher_cluster@learngraph.internal",
            full_name="Prof. Sarah Jenkins",
            hashed_password=hash_password("teacher123"),
            role=UserRole.TEACHER.value,
            is_active=True,
        )
        db.add(teacher)
        db.commit()
        db.refresh(teacher)

    teacher_id = smith.id if smith else (teacher.id if teacher else 1)

    # 2. Ensure or load Assessment
    assessment = None
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    default_title = f"Cluster Demo (Seeded {today_str})"

    if assessment_id is not None:
        assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
        if not assessment:
            raise ValueError(f"Assessment with id {assessment_id} not found.")
    else:
        assessment = (
            db.query(Assessment)
            .filter(Assessment.title == default_title)
            .first()
        )

    if not assessment:
        assessment = Assessment(
            title=default_title,
            description="Diagnostic test evaluating arithmetic operations and inverse proportions.",
            created_by=teacher_id,
        )
        if not dry_run:
            db.add(assessment)
            db.commit()
            db.refresh(assessment)

    # Production Safety: check existing findings count for target assessment
    if assessment.id:
        existing_findings_count = (
            db.query(EvaluationFinding)
            .join(EvaluationRun, EvaluationFinding.run_id == EvaluationRun.id)
            .join(Question, EvaluationRun.question_id == Question.id)
            .filter(Question.assessment_id == assessment.id)
            .count()
        )
        if existing_findings_count > 0 and not force:
            raise ValueError(
                f"Refusing to seed: target assessment #{assessment.id} ('{assessment.title}') already has {existing_findings_count} findings. Pass --force to proceed."
            )

    # Production Safety: dry-run early exit
    if dry_run:
        print(f"[DRY-RUN] Target Assessment: '{assessment.title}' (ID: {assessment.id or 'To be created'})")
        print("[DRY-RUN] Would ensure Demo Teacher: 'demo_teacher_cluster@learngraph.internal'")
        print("[DRY-RUN] Would ensure Learning Topic: 'Foundational Mathematics'")
        print("[DRY-RUN] Would ensure 2 Diagnostic Questions: 'Calculate: 1/2 ÷ 3/4' and 'An item costs $80 after a 20% discount'")
        print("[DRY-RUN] Would seed 4 Student Users: demo_student_cluster_1..4@learngraph.internal")
        print("[DRY-RUN] Would seed 4 Submissions with QuestionAnswers and OCR Extractions")
        print("[DRY-RUN] Would seed 4 EvaluationFindings (2 'Fraction Division', 2 'Reverse Percentage') with accepted review status")
        return assessment

    # 3. Ensure Learning Topic
    topic = (
        db.query(LearningTopic)
        .filter(LearningTopic.name == "Foundational Mathematics")
        .first()
    )
    if not topic:
        topic = LearningTopic(
            name="Foundational Mathematics",
            description="Core arithmetic, rational numbers, and applied percentages.",
        )
        db.add(topic)
        db.commit()
        db.refresh(topic)

    # 4. Ensure Diagnostic Questions
    q_fraction = (
        db.query(Question)
        .filter(
            Question.assessment_id == assessment.id,
            Question.prompt.like("%Calculate: 1/2 ÷ 3/4%"),
        )
        .first()
    )
    if not q_fraction:
        q_fraction = Question(
            assessment_id=assessment.id,
            topic_id=topic.id,
            prompt="Calculate: 1/2 ÷ 3/4. Show full steps.",
            question_type=QuestionType.SHORT_ANSWER.value,
            marks=5.0,
            expected_answer="2/3",
            rubric=json.dumps({
                "criteria": [
                    {"text": "Inverts divisor to 4/3", "marks": 2.5},
                    {"text": "Multiplies numerators and simplifies to 2/3", "marks": 2.5},
                ]
            }),
        )
        db.add(q_fraction)
        db.commit()
        db.refresh(q_fraction)

    q_percent = (
        db.query(Question)
        .filter(
            Question.assessment_id == assessment.id,
            Question.prompt.like("%item costs $80 after a 20% discount%"),
        )
        .first()
    )
    if not q_percent:
        q_percent = Question(
            assessment_id=assessment.id,
            topic_id=topic.id,
            prompt="An item costs $80 after a 20% discount. What was the original price?",
            question_type=QuestionType.SHORT_ANSWER.value,
            marks=5.0,
            expected_answer="$100",
            rubric=json.dumps({
                "criteria": [
                    {"text": "Sets up reverse percentage equation: 0.8 * Original = 80", "marks": 2.5},
                    {"text": "Solves for Original = $100", "marks": 2.5},
                ]
            }),
        )
        db.add(q_percent)
        db.commit()
        db.refresh(q_percent)

    # 5. Define Student Profiles and Misconception Configurations
    student_specs = [
        {
            "email": "student_cluster_1@learngraph.internal",
            "name": "Alice Chen",
            "question": q_fraction,
            "answer_text": "1/2 * 3/4 = 3/8",
            "concept_name": "Fraction Division",
            "linked_concept": "Fraction Division",
            "hypothesis": "Direct multiplication without reciprocation of divisor",
            "evidence_excerpt": "1/2 * 3/4 = 3/8",
            "severity": "high",
        },
        {
            "email": "student_cluster_2@learngraph.internal",
            "name": "Bob Smith",
            "question": q_fraction,
            "answer_text": "To divide fractions I multiplied 1*3 and 2*4 to get 3/8.",
            "concept_name": "Fraction Division",
            "linked_concept": "Fraction Division",
            "hypothesis": "Direct multiplication without reciprocation of divisor",
            "evidence_excerpt": "multiplied 1*3 and 2*4 to get 3/8",
            "severity": "high",
        },
        {
            "email": "student_cluster_3@learngraph.internal",
            "name": "Charlie Davis",
            "question": q_percent,
            "answer_text": "80 + 20% of 80 = 80 + 16 = 96 dollars",
            "concept_name": "Reverse Percentage",
            "linked_concept": "Reverse Percentage",
            "hypothesis": "Additive reverse percentage error",
            "evidence_excerpt": "80 + 20% of 80 = 80 + 16 = 96",
            "severity": "medium",
        },
        {
            "email": "student_cluster_4@learngraph.internal",
            "name": "Diana Prince",
            "question": q_percent,
            "answer_text": "Take 80, add 20% back: 80 * 1.20 = 96",
            "concept_name": "Reverse Percentage",
            "linked_concept": "Reverse Percentage",
            "hypothesis": "Additive reverse percentage error",
            "evidence_excerpt": "80 * 1.20 = 96",
            "severity": "medium",
        },
    ]

    for spec in student_specs:
        student = db.query(User).filter(User.email == spec["email"]).first()
        if not student:
            student = User(
                email=spec["email"],
                full_name=spec["name"],
                hashed_password=hash_password("student123"),
                role=UserRole.STUDENT.value,
                is_active=True,
            )
            db.add(student)
            db.commit()
            db.refresh(student)

        # Check existing submission for idempotency
        sub = (
            db.query(Submission)
            .filter(
                Submission.assessment_id == assessment.id,
                Submission.student_id == student.id,
            )
            .first()
        )
        if not sub:
            sub = Submission(
                assessment_id=assessment.id,
                student_id=student.id,
                status=SubmissionStatus.SUBMITTED.value,
            )
            db.add(sub)
            db.commit()
            db.refresh(sub)

        # Question Answer
        q = spec["question"]
        qa = (
            db.query(QuestionAnswer)
            .filter(
                QuestionAnswer.submission_id == sub.id,
                QuestionAnswer.question_id == q.id,
            )
            .first()
        )
        if not qa:
            qa = QuestionAnswer(
                submission_id=sub.id,
                question_id=q.id,
                answer_text=spec["answer_text"],
            )
            db.add(qa)
            db.commit()
            db.refresh(qa)

        # Upload and OCR records (provenance integrity)
        upload = (
            db.query(AnswerSheetUpload)
            .filter(AnswerSheetUpload.submission_id == sub.id)
            .first()
        )
        if not upload:
            upload = AnswerSheetUpload(
                submission_id=sub.id,
                original_filename=f"cluster_seed_{sub.id}.pdf",
                stored_filename=f"cluster_seed_{sub.id}_stored.pdf",
                storage_path=f"/tmp/cluster_seed_{sub.id}.pdf",
                content_type="application/pdf",
                file_size_bytes=2048,
                upload_status=UploadStatus.EXTRACTED.value,
            )
            db.add(upload)
            db.commit()
            db.refresh(upload)

        ocr = (
            db.query(OCRExtraction)
            .filter(OCRExtraction.upload_id == upload.id)
            .first()
        )
        if not ocr:
            ocr = OCRExtraction(
                upload_id=upload.id,
                extracted_text=spec["answer_text"],
                confidence=0.95,
                provider_name="seed_cluster_demo",
                processing_status="completed",
            )
            db.add(ocr)
            db.commit()
            db.refresh(ocr)

        # Proposal
        proposal = (
            db.query(ProposedAnswer)
            .filter(
                ProposedAnswer.submission_id == sub.id,
                ProposedAnswer.question_id == q.id,
            )
            .first()
        )
        if not proposal:
            proposal = ProposedAnswer(
                submission_id=sub.id,
                upload_id=upload.id,
                ocr_extraction_id=ocr.id,
                question_id=q.id,
                confidence=0.95,
                status="approved",
                proposed_text=spec["answer_text"],
            )
            db.add(proposal)
            db.commit()
            db.refresh(proposal)

        # Evaluation Run
        run = (
            db.query(EvaluationRun)
            .filter(
                EvaluationRun.submission_id == sub.id,
                EvaluationRun.question_id == q.id,
            )
            .first()
        )
        if not run:
            run = EvaluationRun(
                submission_id=sub.id,
                question_id=q.id,
                question_answer_id=qa.id,
                evaluator_name="mock_vllm_cluster_demo",
                status="completed",
                answer_text_hash=f"hash_seed_{sub.id}_{q.id}",
                answer_text_snapshot=spec["answer_text"],
            )
            db.add(run)
            db.commit()
            db.refresh(run)

        # Evaluation Finding (Accepted, requires_teacher_review=False)
        finding = (
            db.query(EvaluationFinding)
            .filter(EvaluationFinding.run_id == run.id)
            .first()
        )
        if not finding:
            finding = EvaluationFinding(
                run_id=run.id,
                topic_id=topic.id,
                concept_name=spec["concept_name"],
                category=FindingCategory.LIKELY_MISCONCEPTION.value,
                confidence=0.92,
                confidence_details={
                    "score": 0.92,
                    "level": "high",
                    "uncertainty_reasons": [],
                },
                rationale=f"Systematic error: {spec['hypothesis']}",
                verdict="incorrect",
                marks_awarded=0,
                max_marks=5,
                marks_reason="Incorrect procedure applied.",
                step_by_step_explanation="Identified systematic procedural breakdown in fundamental rule.",
                evidence_excerpt=spec["evidence_excerpt"],
                misconception_hypothesis=spec["hypothesis"],
                misconceptions=[
                    {
                        "hypothesis": spec["hypothesis"],
                        "evidence_excerpt": spec["evidence_excerpt"],
                        "linked_concept": spec["linked_concept"],
                        "severity": spec["severity"],
                    }
                ],
                requires_teacher_review=False,
                acknowledged_uncertainty=False,
                review_status=FindingReviewStatus.ACCEPTED.value,
            )
            db.add(finding)
            db.commit()
            db.refresh(finding)

    logger.info(
        f"Successfully seeded cluster demo for Assessment #{assessment.id} ('{assessment.title}'): "
        "2 clusters ('Fraction Division', 'Reverse Percentage') across 4 distinct students."
    )
    return assessment


def main():
    parser = argparse.ArgumentParser(
        description="Seed real demo data for class-level misconception aggregation"
    )
    parser.add_argument(
        "--assessment-id",
        type=int,
        default=None,
        help="Optional target assessment ID. If omitted, creates a new diagnostic assessment named 'Cluster Demo (Seeded YYYY-MM-DD)'.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force seeding even if target assessment already has existing evaluation findings.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate execution and print entities that would be created without committing changes to database.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        assessment = seed_cluster_demo(
            db,
            assessment_id=args.assessment_id,
            force=args.force,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            print(f"[DRY-RUN] Seeding simulation finished for Assessment '{assessment.title}'. No database writes were committed.")
        else:
            print(f"Cluster demo seeding complete for Assessment #{assessment.id} ('{assessment.title}').")
    finally:
        db.close()


if __name__ == "__main__":
    main()
