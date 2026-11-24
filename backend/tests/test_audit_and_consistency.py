import hashlib
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.assessment import Assessment, Question
from app.models.enums import (
    FindingReviewAction,
    FindingReviewStatus,
    PracticeItemReviewAction,
    PracticeItemReviewStatus,
    PracticeQuestionType,
    ProposalStatus,
    QuestionType,
    SubmissionStatus,
    UploadStatus,
    UserRole,
)
from app.models.evaluation import EvaluationFinding, EvaluationRun
from app.models.matching import ProposedAnswer
from app.models.ocr import OCRExtraction
from app.models.remediation import RemediationItem, RemediationRun
from app.models.submission import AnswerSheetUpload, QuestionAnswer, Submission
from app.models.topic import LearningTopic
from app.models.user import User
from app.schemas.remediation import RemediationItemStudentRead, RemediationItemTeacherRead
from tests.conftest import auth_headers_for_user


@pytest.fixture
def audit_setup(db_session: Session):
    """
    Sets up a full multi-entity environment for audit verification:
    - Teacher 1 (creator)
    - Teacher 2 (arbitrary teacher)
    - Student Gauss
    - Student Euler
    - Assessment A with Question A1
    - Assessment B with Question B1
    """
    teacher1 = User(
        full_name="Prof. Archimedes",
        email="archimedes@learngraph.edu",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    teacher2 = User(
        full_name="Prof. Hypatia",
        email="hypatia@learngraph.edu",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    student1 = User(
        full_name="Carl Gauss",
        email="gauss@learngraph.edu",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    student2 = User(
        full_name="Leonhard Euler",
        email="euler@learngraph.edu",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    db_session.add_all([teacher1, teacher2, student1, student2])
    db_session.commit()

    topic = LearningTopic(
        name="Linear Algebra",
        description="Vector spaces and matrices",
    )
    db_session.add(topic)
    db_session.commit()

    assessment_a = Assessment(
        title="Linear Algebra Exam 1",
        description="Exam 1 on Matrix Operations",
        created_by=teacher1.id,
    )
    assessment_b = Assessment(
        title="Calculus Exam 1",
        description="Exam 1 on Limits",
        created_by=teacher1.id,
    )
    db_session.add_all([assessment_a, assessment_b])
    db_session.commit()

    q_a1 = Question(
        assessment_id=assessment_a.id,
        topic_id=topic.id,
        question_type=QuestionType.ESSAY.value,
        prompt="Explain what the product rule for differentiation is.",
        marks=10.0,
        expected_answer="The product rule is (fg)' = f'g + fg'.",
        rubric="Full marks for f'g + fg'.",
    )
    q_b1 = Question(
        assessment_id=assessment_b.id,
        topic_id=topic.id,
        question_type=QuestionType.SHORT_ANSWER.value,
        prompt="Compute the limit of sin(x)/x as x approaches 0.",
        marks=5.0,
        expected_answer="1",
        rubric="Full marks for 1.",
    )
    db_session.add_all([q_a1, q_b1])
    db_session.commit()

    submission = Submission(
        assessment_id=assessment_a.id,
        student_id=student1.id,
        status=SubmissionStatus.PROCESSING.value,
    )
    db_session.add(submission)
    db_session.commit()

    return {
        "teacher1": teacher1,
        "teacher2": teacher2,
        "student1": student1,
        "student2": student2,
        "topic": topic,
        "assessment_a": assessment_a,
        "assessment_b": assessment_b,
        "q_a1": q_a1,
        "q_b1": q_b1,
        "submission": submission,
    }


def test_cross_record_relationship_validation(client: TestClient, audit_setup):
    """
    Audit Item 4: Verifies cross-record integrity and relationship validation.
    - Question belonging to Assessment B cannot be evaluated under a submission for Assessment A (422).
    - Question that does not exist returns 404.
    """
    submission_id = audit_setup["submission"].id
    q_b1_id = audit_setup["q_b1"].id
    teacher_headers = auth_headers_for_user(audit_setup["teacher1"])

    # 1. Attempting to get question evaluations for a question belonging to another assessment
    res = client.get(
        f"/api/v1/submissions/{submission_id}/questions/{q_b1_id}/evaluations",
        headers=teacher_headers,
    )
    assert res.status_code == 422
    assert "Question does not belong to the submission's assessment" in res.json()["error"]["message"]

    # 2. Attempting with non-existent question
    res_404 = client.get(
        f"/api/v1/submissions/{submission_id}/questions/999999/evaluations",
        headers=teacher_headers,
    )
    assert res_404.status_code == 404
    assert "not found" in res_404.json()["error"]["message"]


def test_caller_supplied_identity_vulnerabilities(client: TestClient, audit_setup, db_session: Session):
    """
    Step 11 Security Verification: Verifies that caller-supplied identity is no longer trusted.
    1. Unauthenticated request to approve is rejected with 401 Unauthorized.
    2. Student caller attempting teacher approval is rejected with 403 Forbidden.
    3. Authenticated teacher caller succeeds; review records the teacher's identity from the JWT token,
       even if caller attempts to pass a spoofed reviewer_id in payload.
    4. Authenticated student caller creating submission derives student_id from token,
       ignoring any caller-supplied student_id.
    """
    submission = audit_setup["submission"]
    teacher1 = audit_setup["teacher1"]
    teacher2 = audit_setup["teacher2"]
    student1 = audit_setup["student1"]
    student2 = audit_setup["student2"]

    teacher1_headers = auth_headers_for_user(teacher1)
    teacher2_headers = auth_headers_for_user(teacher2)
    student1_headers = auth_headers_for_user(student1)
    student2_headers = auth_headers_for_user(student2)

    # Create an upload and proposed answer for testing reviews
    upload = AnswerSheetUpload(
        submission_id=submission.id,
        original_filename="sample.pdf",
        stored_filename="uuid_sample.pdf",
        storage_path="/tmp/uuid_sample.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
        upload_status=UploadStatus.EXTRACTED.value,
    )
    db_session.add(upload)
    db_session.commit()

    ocr_extraction = OCRExtraction(
        upload_id=upload.id,
        provider_name="mock_ocr_provider",
        processing_status=UploadStatus.EXTRACTED.value,
        extracted_text="Question 1: (fg)' = f'g + fg'",
        confidence=0.92,
        structured_segments=[
            {"segment_id": 1, "page": 1, "text": "Question 1: (fg)' = f'g + fg'", "confidence": 0.92}
        ],
    )
    db_session.add(ocr_extraction)
    db_session.commit()

    match_res = client.post(
        f"/api/v1/submissions/{submission.id}/match-answers",
        headers=teacher1_headers,
    )
    assert match_res.status_code == 200
    proposal_id = match_res.json()["proposals"][0]["id"]

    # 1. Unauthenticated caller -> rejected 401
    res_unauth = client.post(
        f"/api/v1/proposed-answers/{proposal_id}/approve",
        json={"review_notes": "Unauthenticated caller attempt"},
    )
    assert res_unauth.status_code == 401

    # 2. Student caller attempting teacher approval -> rejected 403 Forbidden
    res_forbidden = client.post(
        f"/api/v1/proposed-answers/{proposal_id}/approve",
        json={"review_notes": "Student trying to self-approve"},
        headers=student1_headers,
    )
    assert res_forbidden.status_code == 403

    # 3. Authenticated teacher2 calls approve with spoofed reviewer_id (999999) ->
    # Reviewer identity is derived exclusively from JWT token (teacher2.id), not the payload!
    res_teacher = client.post(
        f"/api/v1/proposed-answers/{proposal_id}/approve",
        json={"reviewer_id": 999999, "review_notes": "Approved by authenticated teacher2"},
        headers=teacher2_headers,
    )
    assert res_teacher.status_code == 200
    assert res_teacher.json()["proposal"]["status"] == "approved"
    assert res_teacher.json()["review"]["reviewer_id"] == teacher2.id

    # 4. Authenticated student2 creates submission with spoofed student_id (student1.id) ->
    # student_id is derived strictly from authenticated user (student2.id)!
    res_sub = client.post(
        f"/api/v1/assessments/{audit_setup['assessment_a'].id}/submissions",
        json={"student_id": student1.id},
        headers=student2_headers,
    )
    assert res_sub.status_code == 201
    assert res_sub.json()["student_id"] == student2.id


def test_teacher_data_privacy_and_student_schema_filtering():
    """
    Audit Item 4: Verifies student data privacy guarantees.
    - RemediationItemStudentRead strictly excludes teacher_answer_key, teacher_rationale,
      and reviewer_id/review_notes.
    - RemediationItemTeacherRead includes these fields for teacher review.
    """
    item_dict = {
        "id": 1,
        "run_id": 10,
        "finding_id": 20,
        "question_type": PracticeQuestionType.EXPLAIN_REASONING.value,
        "question_text": "What does invertibility mean geometrically?",
        "teacher_answer_key": "CONFIDENTIAL: It means the kernel is trivial and range spans Rn.",
        "teacher_rationale": "CONFIDENTIAL: Tests student knowledge of full rank transformation.",
        "target_concept": "Invertibility",
        "difficulty": "medium",
        "review_status": PracticeItemReviewStatus.APPROVED.value,
        "edited_question_text": None,
        "edited_answer_key": None,
        "reviewed_by": 2,
        "reviewed_at": "2026-11-02T00:00:00Z",
        "review_notes": "Looks good.",
        "created_at": "2026-11-02T00:00:00Z",
        "updated_at": "2026-11-02T00:00:00Z",
    }

    # Validate with Student Schema
    student_view = RemediationItemStudentRead.model_validate(item_dict)
    student_data = student_view.model_dump()
    assert "teacher_answer_key" not in student_data
    assert "teacher_rationale" not in student_data
    assert "review_notes" not in student_data
    assert student_data["question_text"] == "What does invertibility mean geometrically?"

    # Validate with Teacher Schema
    teacher_view = RemediationItemTeacherRead.model_validate(item_dict)
    teacher_data = teacher_view.model_dump()
    assert teacher_data["teacher_answer_key"] == "CONFIDENTIAL: It means the kernel is trivial and range spans Rn."
    assert teacher_data["teacher_rationale"] == "CONFIDENTIAL: Tests student knowledge of full rank transformation."


def test_end_to_end_provenance_and_non_destructive_chain(client: TestClient, audit_setup, db_session: Session):
    """
    Audit Item 2 & 4: Full End-to-End trace with provenance and non-destructive verification:
    upload -> OCR -> matching -> teacher review -> evaluation -> finding review -> remediation generation -> remediation review.
    Verifies that:
    1. Every stage records correct foreign keys / provenance references.
    2. Authoritative QuestionAnswer.answer_text is never modified by evaluation or remediation.
    3. Original OCR extracted_text and proposal text remain immutable.
    4. Finding rationale and evidence excerpt remain immutable.
    """
    submission = audit_setup["submission"]
    q_a1 = audit_setup["q_a1"]
    teacher = audit_setup["teacher1"]

    # 1. Upload & Mock OCR Extraction
    upload = AnswerSheetUpload(
        submission_id=submission.id,
        original_filename="student_handwritten.pdf",
        stored_filename="e2e_uuid_scan.pdf",
        storage_path="/tmp/e2e_uuid_scan.pdf",
        content_type="application/pdf",
        file_size_bytes=4096,
        upload_status=UploadStatus.EXTRACTED.value,
    )
    db_session.add(upload)
    db_session.commit()

    ocr_extraction = OCRExtraction(
        upload_id=upload.id,
        provider_name="mock_ocr_provider",
        processing_status=UploadStatus.EXTRACTED.value,
        extracted_text="Question 1: (f*g)' = f'g' is the derivative.",
        confidence=0.91,
        structured_segments=[
            {
                "segment_id": 1,
                "page": 1,
                "text": "Question 1: (f*g)' = f'g' is the derivative.",
                "confidence": 0.91,
            }
        ],
    )
    db_session.add(ocr_extraction)
    db_session.commit()

    initial_extracted_text = ocr_extraction.extracted_text

    teacher_headers = auth_headers_for_user(teacher)

    # 2. Matching -> Proposed Answer
    match_res = client.post(
        f"/api/v1/submissions/{submission.id}/match-answers",
        headers=teacher_headers,
    )
    assert match_res.status_code == 200
    proposals = match_res.json()["proposals"]
    assert len(proposals) == 1
    proposal_id = proposals[0]["id"]
    initial_proposed_text = proposals[0]["proposed_text"]

    # 3. Teacher Review (Approval) -> Writes to QuestionAnswer
    review_res = client.post(
        f"/api/v1/proposed-answers/{proposal_id}/approve",
        json={"review_notes": "Verified student text matches scan."},
        headers=teacher_headers,
    )
    assert review_res.status_code == 200

    qa = (
        db_session.query(QuestionAnswer)
        .filter(QuestionAnswer.submission_id == submission.id, QuestionAnswer.question_id == q_a1.id)
        .first()
    )
    assert qa is not None
    authoritative_answer_text = qa.answer_text
    assert authoritative_answer_text == initial_proposed_text

    # 4. Evaluation Engine
    eval_res = client.post(
        f"/api/v1/submissions/{submission.id}/questions/{q_a1.id}/evaluate",
        headers=teacher_headers,
    )
    assert eval_res.status_code == 200
    eval_run_id = eval_res.json()["id"]
    findings = eval_res.json()["findings"]
    assert len(findings) > 0
    finding_id = findings[0]["id"]
    initial_finding_rationale = findings[0]["rationale"]
    initial_evidence_excerpt = findings[0]["evidence_excerpt"]

    # 5. Teacher Finding Review (Accept)
    finding_review_res = client.post(
        f"/api/v1/evaluations/findings/{finding_id}/review",
        json={
            "action": FindingReviewAction.ACCEPT.value,
            "review_notes": "Confirmed student confused negation with inversion.",
        },
        headers=teacher_headers,
    )
    assert finding_review_res.status_code == 200
    assert finding_review_res.json()["finding"]["review_status"] == FindingReviewStatus.ACCEPTED.value

    # 6. Remediation Generation
    remed_res = client.post(
        f"/api/v1/findings/{finding_id}/remediation/generate",
        headers=teacher_headers,
    )
    assert remed_res.status_code == 200
    remed_run_id = remed_res.json()["id"]
    items = remed_res.json()["items"]
    assert len(items) > 0
    item_id = items[0]["id"]
    initial_item_question = items[0]["question_text"]

    # 7. Remediation Practice Item Review (Teacher Edit)
    item_review_res = client.post(
        f"/api/v1/remediations/items/{item_id}/review",
        json={
            "action": PracticeItemReviewAction.EDIT.value,
            "edited_question_text": "Clarified: What happens when you multiply a matrix by its inverse?",
            "edited_answer_key": "You get the identity matrix I.",
            "review_notes": "Simplified prompt for better clarity.",
        },
        headers=teacher_headers,
    )
    assert item_review_res.status_code == 200
    assert item_review_res.json()["item"]["review_status"] == PracticeItemReviewStatus.EDITED.value

    # --- NON-DESTRUCTIVE VERIFICATION ---
    db_session.refresh(ocr_extraction)
    db_session.refresh(qa)
    eval_run = db_session.query(EvaluationRun).filter(EvaluationRun.id == eval_run_id).first()
    eval_finding = db_session.query(EvaluationFinding).filter(EvaluationFinding.id == finding_id).first()
    remed_item = db_session.query(RemediationItem).filter(RemediationItem.id == item_id).first()

    # Verify original raw OCR text is untouched
    assert ocr_extraction.extracted_text == initial_extracted_text

    # Verify authoritative student answer text was NEVER mutated by evaluation or remediation
    assert qa.answer_text == authoritative_answer_text

    # Verify evaluation snapshot and hash match the authoritative answer
    expected_hash = hashlib.sha256(authoritative_answer_text.strip().encode("utf-8")).hexdigest()
    assert eval_run.answer_text_hash == expected_hash
    assert eval_run.answer_text_snapshot == authoritative_answer_text

    # Verify finding rationale and evidence are unchanged
    assert eval_finding.rationale == initial_finding_rationale
    assert eval_finding.evidence_excerpt == initial_evidence_excerpt

    # Verify remediation item preserved original generated question while storing teacher edits
    assert remed_item.question_text == initial_item_question
    assert remed_item.edited_question_text == "Clarified: What happens when you multiply a matrix by its inverse?"
    assert remed_item.edited_answer_key == "You get the identity matrix I."

    # --- PROVENANCE CHAIN INTEGRITY ---
    assert remed_item.run_id == remed_run_id
    assert remed_item.finding_id == finding_id
    assert eval_finding.run_id == eval_run_id
    assert eval_run.submission_id == submission.id
    assert eval_run.question_id == q_a1.id
    assert eval_run.question_answer_id == qa.id


def test_error_handling_sanitizes_internals(client: TestClient, audit_setup):
    """
    Audit Item 4: Verifies that API errors do not leak internal stack traces or filesystem paths.
    """
    teacher_headers = auth_headers_for_user(audit_setup["teacher1"])
    # Bad request with invalid action enum
    res = client.post(
        "/api/v1/remediations/items/1/review",
        json={"action": "INVALID_ACTION"},
        headers=teacher_headers,
    )
    assert res.status_code == 422
    response_body = res.text
    # Ensure no internal filesystem paths or python traceback details are leaked
    assert "Traceback (most recent call last)" not in response_body
    assert "/home/" not in response_body
    assert ".py" not in response_body
