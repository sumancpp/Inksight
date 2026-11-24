"""
Live End-to-End Verification Script for LearnGraph
Flow:
1. Seed teacher, student, topic, assessment with 2 questions, submission.
2. Upload answer sheet PDF.
3. Trigger OCR background processing (mock adapter).
4. Wait for processing to complete.
5. Trigger answer matching service.
6. Verify proposed answers, unmatched segments, and unanswered questions.
7. Teacher approves proposal 1.
8. Teacher corrects proposal 2.
9. Verify authoritative answers stored in QuestionAnswer.
"""
import io
import time
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.enums import UserRole, QuestionType, SubmissionStatus, UploadStatus
from app.models.user import User
from app.models.topic import LearningTopic
from app.models.assessment import Assessment, Question
from app.models.submission import Submission, QuestionAnswer
from app.models.matching import ProposedAnswer, TeacherReview


def run_verification():
    client = TestClient(app)
    db = SessionLocal()

    print("=== STARTING LIVE END-TO-END VERIFICATION ===")

    # 1. Seed records
    teacher = User(
        full_name="Dr. E2E Teacher",
        email=f"e2e.teacher.{int(time.time())}@learngraph.edu",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    student = User(
        full_name="E2E Student",
        email=f"e2e.student.{int(time.time())}@learngraph.edu",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    db.add_all([teacher, student])
    db.commit()

    topic = LearningTopic(
        name=f"E2E Topic {int(time.time())}",
        description="Live flow verification topic",
    )
    db.add(topic)
    db.commit()

    assessment = Assessment(
        title="E2E Assessment",
        description="Two questions",
        created_by=teacher.id,
    )
    db.add(assessment)
    db.commit()

    q1 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Explain what a derivative measures.",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=5.0,
    )
    q2 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="State the chain rule for (f(g(x)))'.",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=5.0,
    )
    db.add_all([q1, q2])
    db.commit()

    submission = Submission(
        assessment_id=assessment.id,
        student_id=student.id,
        status=SubmissionStatus.SUBMITTED.value,
    )
    db.add(submission)
    db.commit()

    print(f"[OK] Seeded Teacher ({teacher.id}), Student ({student.id}), Assessment ({assessment.id}), Submission ({submission.id})")

    # 2. Upload synthetic answer sheet PDF
    pdf_content = b"%PDF-1.5\n%Synthetic student answer sheet for E2E\n%%EOF\n"
    upload_resp = client.post(
        f"/api/v1/submissions/{submission.id}/answer-sheets",
        files={"file": ("student_sheet.pdf", io.BytesIO(pdf_content), "application/pdf")},
    )
    assert upload_resp.status_code == 201, upload_resp.text
    upload_id = upload_resp.json()["id"]
    print(f"[OK] Uploaded answer sheet -> upload_id={upload_id}")

    # 3. Trigger OCR process (Mock adapter)
    process_resp = client.post(f"/api/v1/answer-sheets/{upload_id}/process")
    assert process_resp.status_code == 202, process_resp.text
    print(f"[OK] Triggered OCR processing -> status={process_resp.json()['status']}")

    # 4. Wait for OCR to complete (Mock is instant background task)
    for _ in range(10):
        status_resp = client.get(f"/api/v1/answer-sheets/{upload_id}/processing-status")
        if status_resp.json()["upload_status"] == UploadStatus.EXTRACTED.value:
            break
        time.sleep(0.1)

    assert status_resp.json()["upload_status"] == UploadStatus.EXTRACTED.value
    print(f"[OK] OCR extraction completed -> status={UploadStatus.EXTRACTED.value}")

    # 5. Trigger Answer Matching
    match_resp = client.post(f"/api/v1/submissions/{submission.id}/match-answers")
    assert match_resp.status_code == 200, match_resp.text
    match_data = match_resp.json()
    print(f"[OK] Matched answers -> matched_count={match_data['matched_count']}, total={match_data['total_questions']}")
    assert len(match_data["proposals"]) >= 2
    p1 = match_data["proposals"][0]
    p2 = match_data["proposals"][1]

    # 6. Retrieve proposed answers
    get_prop_resp = client.get(f"/api/v1/submissions/{submission.id}/proposed-answers")
    assert get_prop_resp.status_code == 200
    print(f"[OK] GET /submissions/{submission.id}/proposed-answers verified")

    # 7. Teacher Approves Proposal 1
    app_resp = client.post(
        f"/api/v1/proposed-answers/{p1['id']}/approve",
        json={"reviewer_id": teacher.id, "review_notes": "Good derivation"},
    )
    assert app_resp.status_code == 200, app_resp.text
    app_data = app_resp.json()
    assert app_data["proposal"]["status"] == "approved"
    assert app_data["review"]["action"] == "approved"
    print(f"[OK] Teacher approved proposal {p1['id']} -> authoritative answer created")

    # 8. Teacher Corrects Proposal 2
    corrected_answer = "f'(g(x)) * g'(x) (Corrected chain rule by teacher)"
    corr_resp = client.post(
        f"/api/v1/proposed-answers/{p2['id']}/correct",
        json={
            "reviewer_id": teacher.id,
            "corrected_text": corrected_answer,
            "review_notes": "Fixed prime notation",
        },
    )
    assert corr_resp.status_code == 200, corr_resp.text
    corr_data = corr_resp.json()
    assert corr_data["proposal"]["status"] == "corrected"
    assert corr_data["proposal"]["corrected_text"] == corrected_answer
    assert corr_data["authoritative_answer_text"] == corrected_answer
    print(f"[OK] Teacher corrected proposal {p2['id']} -> authoritative answer updated")

    # 9. Verify QuestionAnswer authoritative records in DB
    qa1 = db.query(QuestionAnswer).filter(
        QuestionAnswer.submission_id == submission.id,
        QuestionAnswer.question_id == q1.id,
    ).first()
    assert qa1 is not None and qa1.answer_text == p1["proposed_text"]

    qa2 = db.query(QuestionAnswer).filter(
        QuestionAnswer.submission_id == submission.id,
        QuestionAnswer.question_id == q2.id,
    ).first()
    assert qa2 is not None and qa2.answer_text == corrected_answer
    print(f"[OK] Verified authoritative QuestionAnswer records in DB: Q1 and Q2 populated")

    # 10. Audit trail verification
    reviews = db.query(TeacherReview).filter(TeacherReview.submission_id == submission.id).all()
    assert len(reviews) == 2
    print(f"[OK] Verified TeacherReview audit trail: {len(reviews)} review records recorded")

    print("=== LIVE END-TO-END VERIFICATION COMPLETED SUCCESSFULLY ===")
    db.close()


if __name__ == "__main__":
    run_verification()
