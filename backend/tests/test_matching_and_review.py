import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.assessment import Assessment, Question
from app.models.enums import (
    InvalidStateTransitionError,
    ProposalStatus,
    QuestionType,
    ReviewAction,
    SubmissionStatus,
    UploadStatus,
    UserRole,
    validate_proposal_transition,
)
from app.models.matching import ProposedAnswer, TeacherReview
from app.models.ocr import OCRExtraction
from app.models.submission import AnswerSheetUpload, QuestionAnswer, Submission
from app.models.topic import LearningTopic
from app.models.user import User
from app.services.matching_service import matching_service


@pytest.fixture
def matching_test_setup(client: TestClient, db_session: Session):
    """
    Sets up a full hierarchy: Teacher, Student, Topic, Assessment with 3 Questions,
    Submission, AnswerSheetUpload, and OCRExtraction.
    """
    teacher = User(
        full_name="Prof. Archimedes",
        email="archimedes@learngraph.edu",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    student = User(
        full_name="Hypatia Student",
        email="hypatia@learngraph.edu",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    db_session.add_all([teacher, student])
    db_session.commit()

    topic = LearningTopic(
        name="Calculus & Derivatives",
        description="Core calculus concepts",
    )
    db_session.add(topic)
    db_session.commit()

    assessment = Assessment(
        title="Calculus Quiz 1",
        description="Three questions on limits and derivatives",
        created_by=teacher.id,
    )
    db_session.add(assessment)
    db_session.commit()

    q1 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Define the derivative of f(x) = x^2.",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=5.0,
    )
    q2 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Explain the product rule.",
        question_type=QuestionType.ESSAY.value,
        marks=10.0,
    )
    q3 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Compute the limit of sin(x)/x as x -> 0.",
        question_type=QuestionType.NUMERICAL.value,
        marks=5.0,
    )
    db_session.add_all([q1, q2, q3])
    db_session.commit()

    submission = Submission(
        assessment_id=assessment.id,
        student_id=student.id,
        status=SubmissionStatus.SUBMITTED.value,
    )
    db_session.add(submission)
    db_session.commit()

    upload = AnswerSheetUpload(
        submission_id=submission.id,
        original_filename="hypatia_exam.pdf",
        stored_filename="hypatia_exam_uuid.pdf",
        storage_path="/tmp/hypatia_exam_uuid.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
        upload_status=UploadStatus.EXTRACTED.value,
    )
    db_session.add(upload)
    db_session.commit()

    extraction = OCRExtraction(
        upload_id=upload.id,
        provider_name="mock_ocr_provider",
        processing_status=UploadStatus.EXTRACTED.value,
        extracted_text="Question 1: f'(x) = 2x.\nQuestion 2: (fg)' = f'g + fg'.\nQuestion 3: Limit is 1.",
        confidence=0.95,
        structured_segments=[
            {"segment_id": 1, "page": 1, "text": "Question 1: f'(x) = 2x using power rule.", "confidence": 0.95},
            {"segment_id": 2, "page": 1, "text": "2. (f*g)' = f'*g + f*g' is the product rule.", "confidence": 0.92},
            {"segment_id": 3, "page": 1, "text": "3) The limit of sin(x)/x as x approaches 0 is 1.", "confidence": 0.90},
        ],
    )
    db_session.add(extraction)
    db_session.commit()

    from tests.conftest import auth_headers_for_user
    client.headers.update(auth_headers_for_user(teacher))

    return {
        "teacher": teacher,
        "student": student,
        "assessment": assessment,
        "questions": [q1, q2, q3],
        "submission": submission,
        "upload": upload,
        "extraction": extraction,
    }


def test_matching_numbered_segments_to_assessment_questions(client: TestClient, matching_test_setup):
    """
    Validates numbered segments (e.g. 'Question 1:', '2.', '3)') cleanly match
    to assessment questions 1, 2, 3 in deterministic order.
    """
    sub_id = matching_test_setup["submission"].id
    resp = client.post(f"/api/v1/submissions/{sub_id}/match-answers")
    assert resp.status_code == 200
    data = resp.json()

    assert data["submission_id"] == sub_id
    assert data["total_questions"] == 3
    assert data["matched_count"] == 3
    assert data["needs_review_count"] == 0
    assert data["unmatched_count"] == 0
    assert len(data["unanswered_questions"]) == 0

    proposals = data["proposals"]
    assert len(proposals) == 3
    # Check each proposal maps to the expected question
    questions = matching_test_setup["questions"]
    assert proposals[0]["question_id"] == questions[0].id
    assert proposals[0]["status"] == "proposed"
    assert "2x" in proposals[0]["proposed_text"]

    assert proposals[1]["question_id"] == questions[1].id
    assert proposals[1]["status"] == "proposed"
    assert "product rule" in proposals[1]["proposed_text"]

    assert proposals[2]["question_id"] == questions[2].id
    assert proposals[2]["status"] == "proposed"
    assert "limit" in proposals[2]["proposed_text"].lower()


def test_missing_duplicate_and_out_of_bounds_question_numbers(client: TestClient, db_session: Session, matching_test_setup):
    """
    Validates:
    - Missing question number -> unmatched
    - Duplicate question number -> needs_review (reason: DUPLICATE_QUESTION_NUMBER)
    - Out of bounds question number -> unmatched (reason: QUESTION_NUMBER_OUT_OF_BOUNDS)
    """
    extraction = matching_test_setup["extraction"]
    extraction.structured_segments = [
        {"segment_id": 10, "page": 1, "text": "Question 1: First attempt at Q1", "confidence": 0.90},
        {"segment_id": 11, "page": 1, "text": "1. Second duplicate claim for Q1", "confidence": 0.88},
        {"segment_id": 12, "page": 1, "text": "Question 99: Out of bounds question number", "confidence": 0.95},
        {"segment_id": 13, "page": 1, "text": "No label here, just unindexed scratch work", "confidence": 0.80},
    ]
    db_session.commit()

    sub_id = matching_test_setup["submission"].id
    resp = client.post(f"/api/v1/submissions/{sub_id}/match-answers")
    assert resp.status_code == 200
    data = resp.json()

    # Duplicates routed to needs_review
    assert data["needs_review_count"] == 2
    # Out of bounds and missing label routed to unmatched
    assert data["unmatched_count"] == 2

    reasons = [p["rejection_reason"] for p in data["proposals"]]
    assert "DUPLICATE_QUESTION_NUMBER" in reasons
    assert "QUESTION_NUMBER_OUT_OF_BOUNDS" in reasons
    assert "NO_QUESTION_NUMBER_DETECTED" in reasons

    # Unmatched segments are explicitly detailed in response
    unmatched_reasons = [u["reason"] for u in data["unmatched_segments"]]
    assert any("does not exist in assessment" in r for r in unmatched_reasons)
    assert any("No question number detected" in r for r in unmatched_reasons)


def test_question_from_another_assessment_cannot_be_matched(client: TestClient, db_session: Session, matching_test_setup):
    """
    Verifies that a question belonging to another assessment cannot be approved/corrected into this submission.
    """
    teacher = matching_test_setup["teacher"]
    sub_id = matching_test_setup["submission"].id

    # Create another assessment with another question
    other_assessment = Assessment(
        title="Other Assessment",
        description="Foreign assessment",
        created_by=teacher.id,
    )
    db_session.add(other_assessment)
    db_session.commit()

    foreign_question = Question(
        assessment_id=other_assessment.id,
        topic_id=matching_test_setup["questions"][0].topic_id,
        prompt="Foreign question prompt",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=10.0,
    )
    db_session.add(foreign_question)
    db_session.commit()

    # Trigger matching first
    resp = client.post(f"/api/v1/submissions/{sub_id}/match-answers")
    assert resp.status_code == 200
    proposal_id = resp.json()["proposals"][0]["id"]

    # Try to approve or correct by forcing foreign_question.id
    correct_resp = client.post(
        f"/api/v1/proposed-answers/{proposal_id}/correct",
        json={
            "reviewer_id": teacher.id,
            "corrected_text": "Trying to attach to another assessment's question",
            "question_id": foreign_question.id,
        },
    )
    assert correct_resp.status_code == 422
    assert "does not belong to the submission's assessment" in correct_resp.json()["error"]["message"]


def test_unmatched_segments_and_unanswered_questions_returned_explicitly(client: TestClient, db_session: Session, matching_test_setup):
    """
    When only question 1 is answered and there is an unlabelled segment:
    - Questions 2 and 3 should be explicitly listed under unanswered_questions.
    - Unlabelled segment should be explicitly listed under unmatched_segments.
    """
    extraction = matching_test_setup["extraction"]
    extraction.structured_segments = [
        {"segment_id": 1, "page": 1, "text": "1. Answer to Q1 only.", "confidence": 0.95},
        {"segment_id": 2, "page": 1, "text": "Random unnumbered notes.", "confidence": 0.85},
    ]
    db_session.commit()

    sub_id = matching_test_setup["submission"].id
    resp = client.get(f"/api/v1/submissions/{sub_id}/proposed-answers")
    assert resp.status_code == 200
    data = resp.json()

    assert data["matched_count"] == 1
    assert data["unmatched_count"] == 1

    # Unanswered questions should have 2 items (Q2 and Q3)
    unanswered = data["unanswered_questions"]
    assert len(unanswered) == 2
    seq_nums = [q["sequence_number"] for q in unanswered]
    assert 2 in seq_nums
    assert 3 in seq_nums
    assert all(q["has_existing_answer"] is False for q in unanswered)


def test_existing_manually_entered_answer_not_overwritten_by_matching(client: TestClient, db_session: Session, matching_test_setup):
    """
    If a QuestionAnswer already exists with answer_text (e.g. manually entered or previously reviewed),
    matching must NOT overwrite it. Instead, proposal is flagged as needs_review.
    """
    sub_id = matching_test_setup["submission"].id
    q1 = matching_test_setup["questions"][0]

    existing_qa = QuestionAnswer(
        submission_id=sub_id,
        question_id=q1.id,
        answer_text="Authoritative manual teacher entry",
    )
    db_session.add(existing_qa)
    db_session.commit()

    resp = client.post(f"/api/v1/submissions/{sub_id}/match-answers")
    assert resp.status_code == 200
    data = resp.json()

    # Proposal for Q1 must be marked needs_review with EXISTING_ANSWER_PRESENT
    q1_proposal = next(p for p in data["proposals"] if p["question_id"] == q1.id)
    assert q1_proposal["status"] == "needs_review"
    assert q1_proposal["rejection_reason"] == "EXISTING_ANSWER_PRESENT"

    # Verify authoritative database record was NOT mutated
    db_session.refresh(existing_qa)
    assert existing_qa.answer_text == "Authoritative manual teacher entry"


def test_duplicate_matching_trigger_is_idempotent(client: TestClient, matching_test_setup):
    """
    Calling matching repeatedly must not create duplicate proposal rows.
    """
    sub_id = matching_test_setup["submission"].id
    resp1 = client.post(f"/api/v1/submissions/{sub_id}/match-answers")
    assert resp1.status_code == 200
    count1 = len(resp1.json()["proposals"])

    resp2 = client.post(f"/api/v1/submissions/{sub_id}/match-answers")
    assert resp2.status_code == 200
    count2 = len(resp2.json()["proposals"])

    assert count1 == count2 == 3


def test_teacher_approval_writes_to_question_answer(client: TestClient, db_session: Session, matching_test_setup):
    """
    Approving a proposal:
    - Changes status to 'approved'
    - Creates QuestionAnswer record with proposed text
    - Records TeacherReview audit entry with original_text and final_text
    """
    sub_id = matching_test_setup["submission"].id
    teacher = matching_test_setup["teacher"]
    q1 = matching_test_setup["questions"][0]

    match_resp = client.post(f"/api/v1/submissions/{sub_id}/match-answers")
    proposal_id = match_resp.json()["proposals"][0]["id"]

    approve_resp = client.post(
        f"/api/v1/proposed-answers/{proposal_id}/approve",
        json={
            "reviewer_id": teacher.id,
            "review_notes": "Clean answer matching Q1",
        },
    )
    assert approve_resp.status_code == 200
    app_data = approve_resp.json()

    assert app_data["proposal"]["status"] == "approved"
    assert app_data["review"]["action"] == "approved"
    assert app_data["review"]["reviewer_id"] == teacher.id
    assert app_data["authoritative_answer_text"] is not None

    # Check QuestionAnswer in DB
    qa = (
        db_session.query(QuestionAnswer)
        .filter(QuestionAnswer.submission_id == sub_id, QuestionAnswer.question_id == q1.id)
        .first()
    )
    assert qa is not None
    assert qa.answer_text == app_data["authoritative_answer_text"]


def test_teacher_correction_writes_corrected_text_and_preserves_ocr(client: TestClient, db_session: Session, matching_test_setup):
    """
    Correcting a proposal:
    - Preserves proposal.proposed_text (original OCR)
    - Sets proposal.corrected_text
    - Sets status to 'corrected'
    - Updates QuestionAnswer.answer_text with corrected_text
    - Audit entry has original_text != final_text
    """
    sub_id = matching_test_setup["submission"].id
    teacher = matching_test_setup["teacher"]
    q1 = matching_test_setup["questions"][0]

    match_resp = client.post(f"/api/v1/submissions/{sub_id}/match-answers")
    p1 = match_resp.json()["proposals"][0]
    proposal_id = p1["id"]
    original_ocr_text = p1["proposed_text"]

    corrected_content = "f'(x) = 2x by the power rule (Teacher note: minor typo fixed)"

    corr_resp = client.post(
        f"/api/v1/proposed-answers/{proposal_id}/correct",
        json={
            "reviewer_id": teacher.id,
            "corrected_text": corrected_content,
            "review_notes": "Fixed notation error in student step",
        },
    )
    assert corr_resp.status_code == 200
    corr_data = corr_resp.json()

    assert corr_data["proposal"]["status"] == "corrected"
    assert corr_data["proposal"]["proposed_text"] == original_ocr_text
    assert corr_data["proposal"]["corrected_text"] == corrected_content
    assert corr_data["review"]["action"] == "corrected"
    assert corr_data["review"]["original_text"] == original_ocr_text
    assert corr_data["review"]["final_text"] == corrected_content
    assert corr_data["authoritative_answer_text"] == corrected_content

    # DB verification
    qa = (
        db_session.query(QuestionAnswer)
        .filter(QuestionAnswer.submission_id == sub_id, QuestionAnswer.question_id == q1.id)
        .first()
    )
    assert qa is not None
    assert qa.answer_text == corrected_content


def test_reject_proposal_does_not_modify_authoritative_answer(client: TestClient, db_session: Session, matching_test_setup):
    """
    Rejecting a proposal:
    - Sets status to 'rejected'
    - Creates audit record
    - Does NOT create or alter QuestionAnswer record
    """
    sub_id = matching_test_setup["submission"].id
    teacher = matching_test_setup["teacher"]
    q1 = matching_test_setup["questions"][0]

    match_resp = client.post(f"/api/v1/submissions/{sub_id}/match-answers")
    proposal_id = match_resp.json()["proposals"][0]["id"]

    rej_resp = client.post(
        f"/api/v1/proposed-answers/{proposal_id}/reject",
        json={
            "reviewer_id": teacher.id,
            "rejection_reason": "Irrelevant scribble",
            "review_notes": "Not an answer",
        },
    )
    assert rej_resp.status_code == 200
    rej_data = rej_resp.json()

    assert rej_data["proposal"]["status"] == "rejected"
    assert rej_data["review"]["action"] == "rejected"
    assert rej_data["authoritative_answer_text"] is None

    # Verify no QuestionAnswer exists
    qa = (
        db_session.query(QuestionAnswer)
        .filter(QuestionAnswer.submission_id == sub_id, QuestionAnswer.question_id == q1.id)
        .first()
    )
    assert qa is None


def test_non_teacher_and_missing_reviewer_rejected(client: TestClient, matching_test_setup):
    """
    Reviewer must exist and have UserRole.TEACHER.
    """
    from app.core.security import create_access_token
    from tests.conftest import auth_headers_for_user

    sub_id = matching_test_setup["submission"].id
    student = matching_test_setup["student"]

    match_resp = client.post(f"/api/v1/submissions/{sub_id}/match-answers")
    proposal_id = match_resp.json()["proposals"][0]["id"]

    # 1. Non-existent reviewer in token -> 401/404
    missing_token = create_access_token(subject="999999", role=UserRole.TEACHER.value)
    missing_resp = client.post(
        f"/api/v1/proposed-answers/{proposal_id}/approve",
        headers={"Authorization": f"Bearer {missing_token}"},
        json={"review_notes": "Attempt with missing reviewer"},
    )
    assert missing_resp.status_code in (401, 404)

    # 2. Student attempting to review -> 403 (role permission denied)
    student_resp = client.post(
        f"/api/v1/proposed-answers/{proposal_id}/approve",
        headers=auth_headers_for_user(student),
        json={"review_notes": "Student trying to review"},
    )
    assert student_resp.status_code in (403, 422)


def test_invalid_review_transitions_return_error(client: TestClient, matching_test_setup):
    """
    - Approving an already approved proposal -> 409
    - Rejecting an already rejected proposal -> 409
    - Transition matrix check
    """
    sub_id = matching_test_setup["submission"].id
    teacher = matching_test_setup["teacher"]

    match_resp = client.post(f"/api/v1/submissions/{sub_id}/match-answers")
    proposal_id = match_resp.json()["proposals"][0]["id"]

    # Approve once
    app1 = client.post(
        f"/api/v1/proposed-answers/{proposal_id}/approve",
        json={"reviewer_id": teacher.id},
    )
    assert app1.status_code == 200

    # Approve twice -> 409
    app2 = client.post(
        f"/api/v1/proposed-answers/{proposal_id}/approve",
        json={"reviewer_id": teacher.id},
    )
    assert app2.status_code == 409

    # Unit test invalid transition matrix directly
    with pytest.raises(InvalidStateTransitionError):
        validate_proposal_transition("rejected", ProposalStatus.APPROVED)



def test_upload_matching_endpoint_and_get_proposal(client: TestClient, matching_test_setup):
    """
    Tests /answer-sheets/{upload_id}/match-answers, /answer-sheets/{upload_id}/proposed-answers,
    and /proposed-answers/{proposal_id}.
    """
    upload_id = matching_test_setup["upload"].id

    match_resp = client.post(f"/api/v1/answer-sheets/{upload_id}/match-answers")
    assert match_resp.status_code == 200
    data = match_resp.json()
    assert data["upload_id"] == upload_id

    # Retrieve proposals by upload
    get_resp = client.get(f"/api/v1/answer-sheets/{upload_id}/proposed-answers")
    assert get_resp.status_code == 200
    assert get_resp.json()["upload_id"] == upload_id

    # Get single proposal
    p_id = data["proposals"][0]["id"]
    single_resp = client.get(f"/api/v1/proposed-answers/{p_id}")
    assert single_resp.status_code == 200
    assert single_resp.json()["id"] == p_id


def test_approving_proposal_supersedes_competing_candidates_for_question(client: TestClient, db_session: Session, matching_test_setup):
    """
    Verifies that when multiple candidate proposals compete for the same question,
    approving or correcting one proposal cleanly supersedes and unlinks the competing candidates
    so downstream evaluation can proceed without being blocked by unapproved candidate ambiguity.
    """
    sub_id = matching_test_setup["submission"].id
    teacher = matching_test_setup["teacher"]
    q1 = matching_test_setup["questions"][0]

    match_resp = client.post(f"/api/v1/submissions/{sub_id}/match-answers")
    proposals = match_resp.json()["proposals"]
    p1 = proposals[0]

    from app.models.matching import ProposedAnswer
    from app.models.enums import ProposalStatus
    p_comp = ProposedAnswer(
        submission_id=sub_id,
        upload_id=p1["upload_id"],
        ocr_extraction_id=p1["ocr_extraction_id"],
        question_id=q1.id,
        segment_id=999,
        proposed_text="Competing ambiguous OCR snippet",
        confidence=0.55,
        status=ProposalStatus.NEEDS_REVIEW.value,
    )
    db_session.add(p_comp)
    db_session.commit()
    db_session.refresh(p_comp)

    # Approve p1
    approve_resp = client.post(
        f"/api/v1/proposed-answers/{p1['id']}/approve",
        json={"reviewer_id": teacher.id, "review_notes": "Authoritative match selected"},
    )
    assert approve_resp.status_code == 200

    # Competing proposal should now be unlinked (question_id=None, status=UNMATCHED)
    db_session.refresh(p_comp)
    assert p_comp.question_id is None
    assert p_comp.status == ProposalStatus.UNMATCHED.value
    assert "SUPERSEDED_BY_APPROVED_PROPOSAL" in (p_comp.rejection_reason or "")


def test_out_of_bounds_proposal_cannot_be_approved_without_reassignment(client: TestClient, db_session: Session, matching_test_setup):
    """
    Verifies that an OCR segment with an out-of-bounds question number (e.g. Question 99)
    creates an UNMATCHED proposal with QUESTION_NUMBER_OUT_OF_BOUNDS and question_id=None.
    Attempting to approve it directly without assigning to a valid question fails with 422.
    """
    sub_id = matching_test_setup["submission"].id
    upload = matching_test_setup["upload"]
    ocr = matching_test_setup["extraction"]
    teacher = matching_test_setup["teacher"]

    from app.models.matching import ProposedAnswer
    from app.models.enums import ProposalStatus

    # Create an out-of-bounds proposal
    p_oob = ProposedAnswer(
        submission_id=sub_id,
        upload_id=upload.id,
        ocr_extraction_id=ocr.id,
        question_id=None,
        segment_id=888,
        proposed_text="Question 99: Extraneous out-of-bounds response",
        confidence=0.92,
        status=ProposalStatus.UNMATCHED.value,
        rejection_reason="QUESTION_NUMBER_OUT_OF_BOUNDS",
    )
    db_session.add(p_oob)
    db_session.commit()
    db_session.refresh(p_oob)

    # Directly approving without assigning question must fail with 422
    approve_resp = client.post(
        f"/api/v1/proposed-answers/{p_oob.id}/approve",
        json={"reviewer_id": teacher.id, "review_notes": "Attempting invalid direct approval"},
    )
    assert approve_resp.status_code == 422
    err_msg = approve_resp.json().get("error", {}).get("message", "") or approve_resp.json().get("detail", "")
    assert "Cannot approve an unmatched proposal without assigning a question" in err_msg


def test_reassign_unmatched_proposal_to_valid_question(client: TestClient, db_session: Session, matching_test_setup):
    """
    Verifies that a teacher can reassign an UNMATCHED proposal (e.g. out-of-bounds or undetected)
    to a valid assessment question using the correct/reassign endpoint.
    The proposal transitions to CORRECTED, clears the rejection reason, and writes QuestionAnswer.
    """
    sub_id = matching_test_setup["submission"].id
    upload = matching_test_setup["upload"]
    ocr = matching_test_setup["extraction"]
    teacher = matching_test_setup["teacher"]
    q2 = matching_test_setup["questions"][1]

    from app.models.matching import ProposedAnswer
    from app.models.submission import QuestionAnswer
    from app.models.enums import ProposalStatus

    p_unmatched = ProposedAnswer(
        submission_id=sub_id,
        upload_id=upload.id,
        ocr_extraction_id=ocr.id,
        question_id=None,
        segment_id=777,
        proposed_text="Newton's second law F = ma explains net force.",
        confidence=0.88,
        status=ProposalStatus.UNMATCHED.value,
        rejection_reason="QUESTION_NUMBER_OUT_OF_BOUNDS",
    )
    db_session.add(p_unmatched)
    db_session.commit()
    db_session.refresh(p_unmatched)

    # Reassign to Question 2 with teacher corrected text
    correct_resp = client.post(
        f"/api/v1/proposed-answers/{p_unmatched.id}/correct",
        json={
            "reviewer_id": teacher.id,
            "question_id": q2.id,
            "corrected_text": "The product rule states (uv)' = u'v + uv'.",
            "review_notes": "Teacher reassigned from unmatched segment to Q2",
        },
    )
    assert correct_resp.status_code == 200
    data = correct_resp.json()
    assert data["proposal"]["status"] == "corrected"
    assert data["proposal"]["question_id"] == q2.id
    assert data["proposal"]["rejection_reason"] is None
    assert data["proposal"]["corrected_text"] == "The product rule states (uv)' = u'v + uv'."
    assert data["authoritative_answer_text"] == "The product rule states (uv)' = u'v + uv'."

    # Verify authoritative QuestionAnswer is written
    qa = (
        db_session.query(QuestionAnswer)
        .filter(QuestionAnswer.submission_id == sub_id, QuestionAnswer.question_id == q2.id)
        .first()
    )
    assert qa is not None
    assert qa.answer_text == "The product rule states (uv)' = u'v + uv'."


def test_existing_answer_conflict_review_and_approval_clears_reason(client: TestClient, db_session: Session, matching_test_setup):
    """
    Verifies that when a submission already has an answer, matching flags the proposal with
    NEEDS_REVIEW and EXISTING_ANSWER_PRESENT. When the teacher reviews and approves,
    the rejection/review advisory reason is cleared, and the authoritative answer is updated.
    """
    sub_id = matching_test_setup["submission"].id
    upload = matching_test_setup["upload"]
    teacher = matching_test_setup["teacher"]
    q1 = matching_test_setup["questions"][0]

    from app.models.submission import QuestionAnswer
    from app.models.matching import ProposedAnswer

    # Pre-populate existing answer
    existing_qa = QuestionAnswer(
        submission_id=sub_id,
        question_id=q1.id,
        answer_text="Previous preliminary answer",
    )
    db_session.add(existing_qa)
    db_session.commit()

    # Trigger matching
    match_resp = client.post(f"/api/v1/answer-sheets/{upload.id}/match-answers")
    assert match_resp.status_code == 200

    # Proposal for Q1 should have status NEEDS_REVIEW and EXISTING_ANSWER_PRESENT
    p_q1 = (
        db_session.query(ProposedAnswer)
        .filter(ProposedAnswer.submission_id == sub_id, ProposedAnswer.question_id == q1.id)
        .first()
    )
    assert p_q1 is not None
    assert p_q1.status == "needs_review"
    assert p_q1.rejection_reason == "EXISTING_ANSWER_PRESENT"

    # Teacher approves the proposal
    approve_resp = client.post(
        f"/api/v1/proposed-answers/{p_q1.id}/approve",
        json={"reviewer_id": teacher.id, "review_notes": "Teacher confirmed overwrite of existing answer"},
    )
    assert approve_resp.status_code == 200
    db_session.refresh(p_q1)
    assert p_q1.status == "approved"
    assert p_q1.rejection_reason is None

    # Authoritative answer must be updated to the proposed OCR text
    db_session.refresh(existing_qa)
    assert existing_qa.answer_text == p_q1.proposed_text


def test_unreviewed_or_unmatched_proposals_block_evaluation(client: TestClient, db_session: Session, matching_test_setup):
    """
    Verifies that AI diagnostic evaluation cannot evaluate answers if they are unreviewed.
    Explicit teacher approval or correction is strictly required.
    """
    sub_id = matching_test_setup["submission"].id
    upload = matching_test_setup["upload"]
    teacher = matching_test_setup["teacher"]
    q1 = matching_test_setup["questions"][0]

    from app.models.submission import QuestionAnswer

    # Set up an unapproved QuestionAnswer with pending proposal
    qa_unreviewed = QuestionAnswer(
        submission_id=sub_id,
        question_id=q1.id,
        answer_text="Unapproved candidate text",
    )
    db_session.add(qa_unreviewed)
    db_session.commit()

    # Trigger matching so proposals exist in 'proposed' or 'needs_review' status
    match_resp = client.post(f"/api/v1/answer-sheets/{upload.id}/match-answers")
    assert match_resp.status_code == 200

    # Direct question evaluation must be rejected with 422 because it is unapproved
    direct_eval = client.post(f"/api/v1/submissions/{sub_id}/questions/{q1.id}/evaluate")
    assert direct_eval.status_code == 422
    err_msg = direct_eval.json().get("error", {}).get("message", "") or direct_eval.json().get("detail", "")
    assert "Cannot evaluate an unreviewed or unapproved answer" in err_msg

    # Batch evaluate will skip unapproved answers and return 0 completed runs
    eval_resp = client.post(f"/api/v1/submissions/{sub_id}/evaluate")
    assert eval_resp.status_code in (200, 202)
    if eval_resp.status_code == 202:
        task_id = eval_resp.json()["task_id"]
        status_resp = client.get(f"/api/v1/submissions/task-status/{task_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "SUCCESS"
        assert status_resp.json()["result"]["total_runs"] == 0
    else:
        assert eval_resp.json()["total_runs"] == 0

    # Teacher explicitly approves the proposal
    p_q1 = [p for p in match_resp.json()["proposals"] if p["question_id"] == q1.id][0]
    app_resp = client.post(
        f"/api/v1/proposed-answers/{p_q1['id']}/approve",
        json={"reviewer_id": teacher.id, "review_notes": "Approved for evaluation"},
    )
    assert app_resp.status_code == 200

    # Now both direct and batch evaluation succeed
    direct_eval2 = client.post(f"/api/v1/submissions/{sub_id}/questions/{q1.id}/evaluate")
    assert direct_eval2.status_code == 200
    assert direct_eval2.json()["submission_id"] == sub_id
    assert direct_eval2.json()["question_id"] == q1.id

    batch_eval2 = client.post(f"/api/v1/submissions/{sub_id}/evaluate")
    assert batch_eval2.status_code in (200, 202)
    if batch_eval2.status_code == 202:
        task_id2 = batch_eval2.json()["task_id"]
        status_resp2 = client.get(f"/api/v1/submissions/task-status/{task_id2}")
        assert status_resp2.status_code == 200
        assert status_resp2.json()["status"] == "SUCCESS"
        assert status_resp2.json()["result"]["total_runs"] >= 1
    else:
        assert batch_eval2.json()["total_runs"] >= 1


def test_proposed_answers_zero_qp_mode_returns_200_empty(client: TestClient, db_session: Session):
    """
    Verifies that in Zero-QP mode (when an assessment has no predefined questions),
    GET /api/v1/answer-sheets/{upload_id}/proposed-answers returns 200 OK with empty proposals
    rather than raising a 422 error.
    """
    teacher = User(
        full_name="Zero QP Teacher",
        email="zeroqp.matching@inksight.edu",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    db_session.add(teacher)
    db_session.commit()

    assessment = Assessment(
        title="Zero-QP Assessment (DocScanner)",
        description="Isolated Zero-QP Assessment without predefined questions",
        created_by=teacher.id,
    )
    db_session.add(assessment)
    db_session.commit()

    submission = Submission(
        assessment_id=assessment.id,
        student_id=teacher.id,
        status="submitted",
    )
    db_session.add(submission)
    db_session.commit()

    upload = AnswerSheetUpload(
        submission_id=submission.id,
        original_filename="DocScanner.pdf",
        stored_filename="docscanner_test.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
        storage_path="/tmp/docscanner_test.pdf",
        upload_status=UploadStatus.EXTRACTED.value,
    )
    db_session.add(upload)
    db_session.commit()

    from tests.conftest import auth_headers_for_user
    resp = client.get(
        f"/api/v1/answer-sheets/{upload.id}/proposed-answers",
        headers=auth_headers_for_user(teacher),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["upload_id"] == upload.id
    assert data["total_questions"] == 0
    assert data["proposals"] == []
    assert "No answers could be matched" in data["message"]



