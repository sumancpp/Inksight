"""
Live flow verification script for LearnGraph AI Assessment & Misconception Evaluation Engine.
Verifies:
1. Create Teacher, Student, Topic, Assessment with Rubric & Expected Answer, Submission.
2. Create Teacher-approved QuestionAnswer record.
3. Trigger evaluation via EvaluationService / API endpoint.
4. Retrieve findings and verify provenance (answer_text_hash, answer_snapshot).
5. Teacher reviews the finding (accepts with notes).
6. Verify finding status and audit log in DB.
7. Clean up test records.
"""
import asyncio
import sys
import os

# Ensure backend is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal
from app.models import (
    AnswerSheetUpload,
    Assessment,
    EvaluationFinding,
    EvaluationRun,
    FindingReviewAudit,
    LearningTopic,
    OCRExtraction,
    ProposedAnswer,
    Question,
    QuestionAnswer,
    Submission,
    TeacherReview,
    User,
)
from app.models.enums import (
    UserRole,
    QuestionType,
    SubmissionStatus,
    UploadStatus,
    ProposalStatus,
    ReviewAction,
    EvaluationStatus,
    FindingCategory,
    FindingReviewStatus,
    FindingReviewAction,
)
from app.services.evaluation_service import evaluation_service
from app.schemas.evaluation import FindingReviewRequest


async def run_live_verification():
    db = SessionLocal()
    print("=" * 70)
    print("STARTING LIVE EVALUATION FLOW VERIFICATION")
    print("=" * 70)

    created_ids = {}

    try:
        # 1. Setup entities
        teacher = User(email="eval_verifier_teacher@learngraph.edu", full_name="Dr. Evaluator", role=UserRole.TEACHER.value)
        student = User(email="eval_verifier_student@learngraph.edu", full_name="Alice Student", role=UserRole.STUDENT.value)
        db.add_all([teacher, student])
        db.flush()
        created_ids["teacher_id"] = teacher.id
        created_ids["student_id"] = student.id
        print(f"[OK] Created Teacher (id={teacher.id}) and Student (id={student.id})")

        topic = LearningTopic(name="Product Rule in Calculus", description="Calculus differentiation rules")
        db.add(topic)
        db.flush()
        created_ids["topic_id"] = topic.id

        assessment = Assessment(title="Calculus Quiz 1", description="Calculus diagnostic assessment", created_by=teacher.id)
        db.add(assessment)
        db.flush()
        created_ids["assessment_id"] = assessment.id

        question = Question(
            assessment_id=assessment.id,
            topic_id=topic.id,
            prompt="State the product rule for differentiating f(x) * g(x).",
            rubric="State (fg)' = f'g + fg' correctly and identify each term.",
            expected_answer="(f*g)' = f'(x)g(x) + f(x)g'(x)",
            marks=5.0,
            question_type=QuestionType.SHORT_ANSWER.value,
        )
        db.add(question)
        db.flush()
        created_ids["question_id"] = question.id
        print(f"[OK] Created Assessment (id={assessment.id}) with Question (id={question.id}, rubric and expected_answer set)")

        submission = Submission(assessment_id=assessment.id, student_id=student.id, status=SubmissionStatus.PROCESSING.value)
        db.add(submission)
        db.flush()
        created_ids["submission_id"] = submission.id

        upload = AnswerSheetUpload(
            submission_id=submission.id,
            original_filename="calc_live.pdf",
            stored_filename="calc_live_uuid.pdf",
            storage_path="/tmp/calc_live_uuid.pdf",
            content_type="application/pdf",
            file_size_bytes=2048,
            upload_status=UploadStatus.EXTRACTED.value,
        )
        db.add(upload)
        db.flush()
        created_ids["upload_id"] = upload.id

        student_answer = "(fg)' = f' * g' because the derivative distributes across multiplication."
        extraction = OCRExtraction(
            upload_id=upload.id,
            provider_name="mock_ocr_provider",
            processing_status=UploadStatus.EXTRACTED.value,
            extracted_text=f"1. {student_answer}",
            confidence=0.95,
            structured_segments=[
                {"segment_id": 1, "page": 1, "text": student_answer, "confidence": 0.95},
            ],
        )
        db.add(extraction)
        db.flush()
        created_ids["extraction_id"] = extraction.id

        # 2. Add Authoritative QuestionAnswer with explicit teacher approval
        qa = QuestionAnswer(
            submission_id=submission.id,
            question_id=question.id,
            answer_text=student_answer,
        )
        db.add(qa)
        db.flush()
        created_ids["qa_id"] = qa.id

        prop = ProposedAnswer(
            submission_id=submission.id,
            upload_id=upload.id,
            ocr_extraction_id=extraction.id,
            question_id=question.id,
            segment_id=1,
            proposed_text=student_answer,
            status=ProposalStatus.APPROVED.value,
            confidence=0.92,
        )
        db.add(prop)
        db.flush()
        created_ids["prop_id"] = prop.id

        treview = TeacherReview(
            proposal_id=prop.id,
            submission_id=submission.id,
            question_id=question.id,
            reviewer_id=teacher.id,
            action=ReviewAction.APPROVE.value,
            original_text=student_answer,
            final_text=student_answer,
            review_notes="Approved verified student handwriting.",
        )
        db.add(treview)
        db.commit()
        print(f"[OK] Created Submission (id={submission.id}), QA (id={qa.id}), and TeacherReview (id={treview.id})")

        # 3. Trigger Evaluation
        expected_hash = evaluation_service.compute_answer_hash(student_answer)
        print(f"\n[TRIGGER] Running evaluation engine for Submission {submission.id}, Question {question.id}...")
        run = await evaluation_service.evaluate_question_answer(db, submission.id, question.id)

        print(f"[OK] EvaluationRun created:")
        print(f"     ID: {run.id}")
        print(f"     Status: {run.status}")
        print(f"     Evaluator: {run.evaluator_name}")
        print(f"     Answer text hash: {run.answer_text_hash}")
        print(f"     Snapshot: '{run.answer_text_snapshot}'")
        assert run.answer_text_hash == expected_hash, "Hash mismatch!"
        assert run.status == EvaluationStatus.COMPLETED.value
        assert len(run.findings) > 0, "No findings generated!"

        finding = run.findings[0]
        created_ids["run_id"] = run.id
        created_ids["finding_id"] = finding.id

        print(f"\n[OK] Finding generated:")
        print(f"     ID: {finding.id}")
        print(f"     Category: {finding.category}")
        print(f"     Evidence excerpt: '{finding.evidence_excerpt}'")
        print(f"     Rationale: '{finding.rationale}'")
        print(f"     Confidence: {finding.confidence} (Uncertainty: {finding.uncertainty_rationale})")
        print(f"     Review status: {finding.review_status}")

        assert finding.category == FindingCategory.LIKELY_MISCONCEPTION.value
        assert "f' * g'" in finding.evidence_excerpt
        assert 0.0 <= finding.confidence <= 1.0

        # 4. Teacher reviews finding
        print(f"\n[REVIEW] Teacher {teacher.id} accepts finding {finding.id} with pedagogical notes...")
        review_req = FindingReviewRequest(
            reviewer_id=teacher.id,
            action=FindingReviewAction.ACCEPT,
            review_notes="Confirmed diagnosis. Recommended targeted practice on derivative Leibniz rule.",
        )
        review_result = evaluation_service.review_finding(db, finding.id, review_req)

        print(f"[OK] Finding review processed:")
        print(f"     New Status: {review_result.finding.review_status}")
        print(f"     Reviewed By: {review_result.finding.reviewed_by}")
        print(f"     Audit Action: {review_result.audit.action}")
        print(f"     Audit Notes: '{review_result.audit.review_notes}'")

        assert review_result.finding.review_status == FindingReviewStatus.ACCEPTED.value
        assert review_result.finding.reviewed_by == teacher.id

        # 5. Verify Idempotency
        print(f"\n[IDEMPOTENCY] Re-triggering evaluation for unchanged answer...")
        duplicate_run = await evaluation_service.evaluate_question_answer(db, submission.id, question.id)
        assert duplicate_run.id == run.id, f"Expected idempotent run {run.id}, got {duplicate_run.id}"
        print(f"[OK] Idempotent evaluation returned existing run {duplicate_run.id}")

        print("\n" + "=" * 70)
        print("ALL LIVE VERIFICATION CHECKS PASSED PERFECTLY!")
        print("=" * 70)

    finally:
        # Cleanup test records
        try:
            print("\nCleaning up live verification test records...")
            db.rollback()
            if "finding_id" in created_ids:
                db.query(FindingReviewAudit).filter(FindingReviewAudit.finding_id == created_ids["finding_id"]).delete()
                db.query(EvaluationFinding).filter(EvaluationFinding.id == created_ids["finding_id"]).delete()
            if "run_id" in created_ids:
                db.query(EvaluationRun).filter(EvaluationRun.id == created_ids["run_id"]).delete()
            if "prop_id" in created_ids:
                db.query(TeacherReview).filter(TeacherReview.proposal_id == created_ids["prop_id"]).delete()
                db.query(ProposedAnswer).filter(ProposedAnswer.id == created_ids["prop_id"]).delete()
            if "qa_id" in created_ids:
                db.query(QuestionAnswer).filter(QuestionAnswer.id == created_ids["qa_id"]).delete()
            if "extraction_id" in created_ids:
                db.query(OCRExtraction).filter(OCRExtraction.id == created_ids["extraction_id"]).delete()
            if "upload_id" in created_ids:
                db.query(AnswerSheetUpload).filter(AnswerSheetUpload.id == created_ids["upload_id"]).delete()
            if "submission_id" in created_ids:
                db.query(Submission).filter(Submission.id == created_ids["submission_id"]).delete()
            if "question_id" in created_ids:
                db.query(Question).filter(Question.id == created_ids["question_id"]).delete()
            if "assessment_id" in created_ids:
                db.query(Assessment).filter(Assessment.id == created_ids["assessment_id"]).delete()
            if "topic_id" in created_ids:
                db.query(LearningTopic).filter(LearningTopic.id == created_ids["topic_id"]).delete()
            if "teacher_id" in created_ids:
                db.query(User).filter(User.id == created_ids["teacher_id"]).delete()
            if "student_id" in created_ids:
                db.query(User).filter(User.id == created_ids["student_id"]).delete()
            db.commit()
            print("[OK] Test records cleaned up successfully.")
        except Exception as e:
            print(f"[WARN] Cleanup error: {e}")
            db.rollback()
        finally:
            db.close()


if __name__ == "__main__":
    asyncio.run(run_live_verification())
