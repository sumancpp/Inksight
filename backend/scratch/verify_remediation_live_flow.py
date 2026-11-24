"""
Live flow verification script for LearnGraph Targeted Follow-up & Remediation Generation Service.
Verifies:
1. Setup: Teacher, Student, Topic, Assessment with rubric, Submission, approved QA.
2. Evaluation run: produces a likely_misconception finding.
3. Teacher accepts the finding.
4. Trigger remediation generation: generates practice items targeting the concept.
5. Verify practice items, provenance, and separation of teacher answer key.
6. Teacher reviews & edits a practice item (stores edit separately, verifies audit entry).
7. Teacher approves the edited practice item.
8. Verify student-facing schema exclusion boundary.
9. Verify idempotency.
10. Clean up test records.
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
    PracticeItemReviewAction,
    PracticeItemReviewStatus,
    ProposedAnswer,
    Question,
    QuestionAnswer,
    RemediationItem,
    RemediationItemAudit,
    RemediationRun,
    RemediationRunStatus,
    Submission,
    TeacherReview,
    User,
)
from app.models.enums import (
    EvaluationStatus,
    FindingCategory,
    FindingReviewAction,
    FindingReviewStatus,
    ProposalStatus,
    QuestionType,
    ReviewAction,
    SubmissionStatus,
    UploadStatus,
    UserRole,
)
from app.schemas.remediation import (
    PracticeItemReviewRequest,
    RemediationItemStudentRead,
)
from app.services.evaluation_service import evaluation_service
from app.services.remediation_service import remediation_service


async def run_live_verification():
    db = SessionLocal()
    print("=" * 70)
    print("STARTING LIVE TARGETED REMEDIATION FLOW VERIFICATION")
    print("=" * 70)

    created_ids = {}

    try:
        # 1. Setup entities
        teacher = User(
            email="remed_live_teacher@learngraph.edu",
            full_name="Dr. Remediation Mentor",
            role=UserRole.TEACHER.value,
        )
        student = User(
            email="remed_live_student@learngraph.edu",
            full_name="Bob Student",
            role=UserRole.STUDENT.value,
        )
        db.add_all([teacher, student])
        db.flush()
        created_ids["teacher_id"] = teacher.id
        created_ids["student_id"] = student.id
        print(f"[OK] Created Teacher (id={teacher.id}) and Student (id={student.id})")

        topic = LearningTopic(
            name="Differential Calculus Product Rule",
            description="Derivative calculus rules and applications",
        )
        db.add(topic)
        db.flush()
        created_ids["topic_id"] = topic.id

        assessment = Assessment(
            title="Calculus Quiz 2 - Product Rule",
            description="Testing Leibniz product rule",
            created_by=teacher.id,
        )
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

        submission = Submission(
            assessment_id=assessment.id,
            student_id=student.id,
            status=SubmissionStatus.PROCESSING.value,
        )
        db.add(submission)
        db.flush()
        created_ids["submission_id"] = submission.id

        upload = AnswerSheetUpload(
            submission_id=submission.id,
            original_filename="calc_remed_live.pdf",
            stored_filename="calc_remed_live_uuid.pdf",
            storage_path="/tmp/calc_remed_live_uuid.pdf",
            content_type="application/pdf",
            file_size_bytes=2048,
            upload_status=UploadStatus.EXTRACTED.value,
        )
        db.add(upload)
        db.flush()
        created_ids["upload_id"] = upload.id

        student_answer = "(fg)' = f' * g' because derivative distributes across factors."
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
            review_notes="Approved student handwriting.",
        )
        db.add(treview)
        db.commit()

        # 2. Evaluate answer
        eval_run = await evaluation_service.evaluate_question_answer(db, submission.id, question.id)
        assert eval_run.status == EvaluationStatus.COMPLETED
        assert len(eval_run.findings) > 0
        finding = eval_run.findings[0]
        created_ids["eval_run_id"] = eval_run.id
        created_ids["finding_id"] = finding.id
        print(f"[OK] EvaluationRun {eval_run.id} created with finding {finding.id} (Category: {finding.category})")

        # 3. Teacher accepts the finding
        from app.schemas.evaluation import FindingReviewRequest
        rev_req = FindingReviewRequest(
            reviewer_id=teacher.id,
            action=FindingReviewAction.ACCEPT,
            review_notes="Accepted product rule misconception.",
        )
        eval_rev = evaluation_service.review_finding(db, finding.id, rev_req)
        assert eval_rev.finding.review_status == FindingReviewStatus.ACCEPTED.value
        print(f"[OK] Teacher {teacher.id} accepted finding {finding.id}")

        # 4. Trigger Remediation Generation
        print(f"\n[TRIGGER] Generating targeted practice items for Finding {finding.id}...")
        remed_run = await remediation_service.generate_remediation_for_finding(db, finding.id)
        created_ids["remed_run_id"] = remed_run.id

        print(f"[OK] RemediationRun created:")
        print(f"     ID: {remed_run.id}")
        print(f"     Generator: {remed_run.generator_name}")
        print(f"     Status: {remed_run.status}")
        print(f"     Items Count: {len(remed_run.items)}")
        assert remed_run.status == RemediationRunStatus.COMPLETED
        assert len(remed_run.items) == 2

        item1 = remed_run.items[0]
        item2 = remed_run.items[1]
        created_ids["item1_id"] = item1.id
        created_ids["item2_id"] = item2.id

        print(f"\n[OK] Practice Item 1 (Multiple Choice):")
        print(f"     ID: {item1.id}")
        print(f"     Type: {item1.question_type}")
        print(f"     Prompt: '{item1.question_text}'")
        print(f"     Options: {item1.options}")
        print(f"     Teacher Key: '{item1.teacher_answer_key}'")
        print(f"     Teacher Rationale: '{item1.teacher_rationale}'")
        assert item1.question_type.value == "multiple_choice"
        assert item1.teacher_answer_key is not None

        print(f"\n[OK] Practice Item 2 (Explain Reasoning):")
        print(f"     ID: {item2.id}")
        print(f"     Type: {item2.question_type}")
        print(f"     Prompt: '{item2.question_text}'")
        print(f"     Teacher Key: '{item2.teacher_answer_key}'")
        assert item2.question_type.value == "explain_reasoning"

        # 5. Teacher Reviews and Edits Item 1
        print(f"\n[REVIEW] Teacher {teacher.id} edits Practice Item {item1.id}...")
        edit_req = PracticeItemReviewRequest(
            reviewer_id=teacher.id,
            action=PracticeItemReviewAction.EDIT,
            edited_question_text="Refined: What is d/dx [f(x)g(x)] under the Leibniz product rule?",
            edited_answer_key="B) f'(x)g(x) + f(x)g'(x)",
            review_notes="Refined wording for clarity.",
        )
        edit_resp = remediation_service.review_practice_item(db, item1.id, edit_req)
        assert edit_resp.item.review_status == PracticeItemReviewStatus.EDITED
        assert edit_resp.item.question_text == item1.question_text  # Original is pristine!
        assert edit_resp.item.edited_question_text == "Refined: What is d/dx [f(x)g(x)] under the Leibniz product rule?"
        assert edit_resp.item.effective_question_text == "Refined: What is d/dx [f(x)g(x)] under the Leibniz product rule?"
        assert edit_resp.audit.action == PracticeItemReviewAction.EDIT
        print(f"[OK] Practice item edited (original prompt preserved, effective prompt updated)")

        # 6. Teacher Approves Edited Item 1
        print(f"\n[APPROVE] Teacher {teacher.id} approves Practice Item {item1.id}...")
        approve_req = PracticeItemReviewRequest(
            reviewer_id=teacher.id,
            action=PracticeItemReviewAction.APPROVE,
            review_notes="Approved for student remediation.",
        )
        approve_resp = remediation_service.review_practice_item(db, item1.id, approve_req)
        assert approve_resp.item.review_status == PracticeItemReviewStatus.APPROVED
        print(f"[OK] Practice item approved. New review_status='{approve_resp.item.review_status.value}'")

        # 7. Verify Student View Boundary
        student_view = RemediationItemStudentRead.model_validate(approve_resp.item)
        student_dict = student_view.model_dump()
        assert "teacher_answer_key" not in student_dict
        assert "teacher_rationale" not in student_dict
        assert "review_notes" not in student_dict
        print(f"[OK] Verified Student View Boundary: teacher keys and rationales are strictly hidden.")

        # 8. Verify Idempotency
        print(f"\n[IDEMPOTENCY] Re-triggering generation for finding {finding.id}...")
        duplicate_run = await remediation_service.generate_remediation_for_finding(db, finding.id)
        assert duplicate_run.id == remed_run.id
        print(f"[OK] Idempotent generation returned existing run {duplicate_run.id}")

        print("\n" + "=" * 70)
        print("ALL LIVE REMEDIATION VERIFICATION CHECKS PASSED PERFECTLY!")
        print("=" * 70)

    finally:
        # Cleanup test records
        try:
            print("\nCleaning up live verification test records...")
            db.rollback()
            if "item1_id" in created_ids or "item2_id" in created_ids:
                db.query(RemediationItemAudit).filter(
                    RemediationItemAudit.item_id.in_([created_ids.get("item1_id", 0), created_ids.get("item2_id", 0)])
                ).delete(synchronize_session=False)
                db.query(RemediationItem).filter(
                    RemediationItem.id.in_([created_ids.get("item1_id", 0), created_ids.get("item2_id", 0)])
                ).delete(synchronize_session=False)
            if "remed_run_id" in created_ids:
                db.query(RemediationRun).filter(RemediationRun.id == created_ids["remed_run_id"]).delete()
            if "finding_id" in created_ids:
                db.query(FindingReviewAudit).filter(FindingReviewAudit.finding_id == created_ids["finding_id"]).delete()
                db.query(EvaluationFinding).filter(EvaluationFinding.id == created_ids["finding_id"]).delete()
            if "eval_run_id" in created_ids:
                db.query(EvaluationRun).filter(EvaluationRun.id == created_ids["eval_run_id"]).delete()
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
