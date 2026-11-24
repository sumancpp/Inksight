import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.assessment import Assessment, Question
from app.models.enums import (
    FindingCategory,
    ProposalStatus,
    QuestionType,
    ReviewAction,
    SubmissionStatus,
    UploadStatus,
    UserRole,
)
from app.models.matching import ProposedAnswer, TeacherReview
from app.models.ocr import OCRExtraction
from app.models.submission import AnswerSheetUpload, QuestionAnswer, Submission
from app.models.topic import LearningTopic
from app.models.user import User
from app.services.evaluator.base import EvaluationInput
from app.services.evaluator.mock_evaluator import MockEvaluator
from app.services.matching_service import matching_service
from tests.conftest import auth_headers_for_user


@pytest.fixture
def diagnostic_env(client: TestClient, db_session: Session):
    teacher = User(
        full_name="Dr. Euler",
        email="euler@learngraph.edu",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    student = User(
        full_name="Gauss Student",
        email="gauss@learngraph.edu",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    db_session.add_all([teacher, student])
    db_session.commit()

    topic = LearningTopic(
        name="Elementary Arithmetic & Calculus",
        description="Addition and differentiation",
    )
    db_session.add(topic)
    db_session.commit()

    assessment = Assessment(
        title="Diagnostic Math Exam",
        description="Arithmetic, calculus, and linear algebra",
        created_by=teacher.id,
    )
    db_session.add(assessment)
    db_session.commit()

    # Q1: Arithmetic
    q1 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Calculate: 2 + 3 = ?",
        question_type=QuestionType.NUMERICAL.value,
        marks=1.0,
        expected_answer="5",
        rubric="Award 1 mark for exact numerical value 5. 0 marks otherwise.",
    )
    # Q2: Worked Calculus
    q2 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Differentiate f(g(x)) using the chain rule.",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=10.0,
        expected_answer="f'(g(x)) * g'(x)",
        rubric="Award 10 marks for f'(g(x)) * g'(x). Partial credit of 5 marks if outer derivative is correct but inner derivative is omitted.",
    )
    # Q3: Linear Algebra (for testing content mismatch)
    q3 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Is the identity matrix invertible? Explain using determinant.",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=5.0,
        expected_answer="Yes, det(I) = 1 != 0, so identity matrix is invertible.",
        rubric="Full marks for confirming invertibility with det(I)=1.",
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

    return {
        "teacher": teacher,
        "student": student,
        "topic": topic,
        "assessment": assessment,
        "q1": q1,
        "q2": q2,
        "q3": q3,
        "submission": submission,
    }


@pytest.mark.anyio
async def test_arithmetic_evaluation_incorrect_error_amount_and_explanation():
    """
    Test 2 + 3 = ? with student answer 6.
    Expected:
    - Verdict: Incorrect
    - Correct answer: 5
    - Error amount: +1
    - Explanation: "2 + 3 means adding 2 and 3, which gives 5. The student wrote 6, so the answer is one too high."
    - Marks: 0 out of 1.0
    - Evidence: "6"
    """
    evaluator = MockEvaluator()
    payload = EvaluationInput(
        question_prompt="Calculate: 2 + 3 = ?",
        expected_answer="5",
        rubric="Award 1 mark for 5.",
        student_answer="6",
        marks=1.0,
        topic_name="Elementary Arithmetic",
    )

    result = await evaluator.evaluate(payload)
    assert len(result.findings) == 1
    f = result.findings[0]

    assert f.verdict == "incorrect"
    assert f.correct_answer == "5"
    assert f.error_amount == "+1"
    assert f.marks_awarded == 0.0
    assert f.max_marks == 1.0
    assert "2 + 3 means adding 2 and 3, which gives 5" in f.step_by_step_explanation
    assert "The student wrote 6, so the answer is one too high." in f.step_by_step_explanation
    assert f.evidence_excerpt == "6"
    assert f.category == FindingCategory.LIKELY_MISCONCEPTION
    assert f.remediation_concept == "Basic Addition & Arithmetic"
    assert f.follow_up_question == "What is 3 + 4 = ?"


@pytest.mark.anyio
async def test_arithmetic_evaluation_correct():
    """
    Test 2 + 3 = ? with student answer 5.
    Expected:
    - Verdict: Correct
    - Correct answer: 5
    - Marks: 1.0 / 1.0
    """
    evaluator = MockEvaluator()
    payload = EvaluationInput(
        question_prompt="Calculate: 2 + 3 = ?",
        expected_answer="5",
        rubric="Award 1 mark for 5.",
        student_answer="5",
        marks=1.0,
        topic_name="Elementary Arithmetic",
    )

    result = await evaluator.evaluate(payload)
    assert len(result.findings) == 1
    f = result.findings[0]

    assert f.verdict == "correct"
    assert f.correct_answer == "5"
    assert f.marks_awarded == 1.0
    assert f.max_marks == 1.0
    assert f.category == FindingCategory.CORRECT_UNDERSTANDING
    assert f.error_amount is None


@pytest.mark.anyio
async def test_worked_solution_partial_credit():
    """
    Test worked chain rule problem with omitted inner derivative.
    Expected:
    - Verdict: partially_correct
    - Partial marks (5.0 / 10.0)
    - Step-by-step points out omitted inner derivative
    """
    evaluator = MockEvaluator()
    payload = EvaluationInput(
        question_prompt="Differentiate f(g(x)) using the chain rule.",
        expected_answer="f'(g(x)) * g'(x)",
        rubric="Award 10 marks for f'(g(x)) * g'(x). 5 marks for f'(g(x)).",
        student_answer="f'(g(x))",
        marks=10.0,
        topic_name="Chain Rule",
    )

    result = await evaluator.evaluate(payload)
    assert len(result.findings) == 1
    f = result.findings[0]

    assert f.verdict == "partially_correct"
    assert f.marks_awarded == 5.0
    assert f.max_marks == 10.0
    assert f.error_type == "missing_step"
    assert "Step 1: Differentiate outer function" in f.step_by_step_explanation
    assert "Missing in student response" in f.step_by_step_explanation
    assert f.follow_up_question is not None


@pytest.mark.anyio
async def test_missing_reference_answer_or_rubric_yields_needs_review():
    """
    When rubric and expected answer are missing, evaluator safely outputs
    category=insufficient_evidence and verdict=needs_teacher_review without inventing standards.
    """
    evaluator = MockEvaluator()
    payload = EvaluationInput(
        question_prompt="Solve the advanced differential equation.",
        expected_answer=None,
        rubric=None,
        student_answer="y = e^x",
        marks=5.0,
    )

    result = await evaluator.evaluate(payload)
    assert len(result.findings) == 1
    f = result.findings[0]

    assert f.category == FindingCategory.INSUFFICIENT_EVIDENCE
    assert f.verdict == "needs_teacher_review"
    assert f.marks_awarded == 0.0
    assert "lacks teacher-provided rubric criteria" in f.rationale


def test_content_mismatch_detection_in_matching(client: TestClient, db_session: Session, diagnostic_env):
    """
    Verifies that a student answer with calculus content matched to a linear algebra matrix question
    is flagged with CONTENT_MISMATCH_SUSPECTED and status NEEDS_REVIEW, rather than auto-matched.
    """
    env = diagnostic_env
    sub = env["submission"]

    upload = AnswerSheetUpload(
        submission_id=sub.id,
        original_filename="calc_on_linear_algebra.pdf",
        stored_filename="calc_on_la_uuid.pdf",
        storage_path="/tmp/calc_on_la_uuid.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
        upload_status=UploadStatus.EXTRACTED.value,
    )
    db_session.add(upload)
    db_session.commit()

    # Segment 3 claims "Question 3: The derivative of f(x) = x^2 is f'(x) = 2x."
    # But Question 3 is "Is the identity matrix invertible?" (Linear Algebra)
    extraction = OCRExtraction(
        upload_id=upload.id,
        provider_name="mock_ocr",
        processing_status=UploadStatus.EXTRACTED.value,
        extracted_text="Question 3: The derivative of f(x) = x^2 is f'(x) = 2x.",
        confidence=0.95,
        structured_segments=[
            {
                "segment_id": 1,
                "page": 1,
                "text": "Question 3: The derivative of f(x) = x^2 is f'(x) = 2x using the power rule.",
                "confidence": 0.95,
            }
        ],
    )
    db_session.add(extraction)
    db_session.commit()

    headers = auth_headers_for_user(env["teacher"])
    resp = client.post(
        f"/api/v1/submissions/{sub.id}/match-answers?upload_id={upload.id}",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    # Verify that the proposal for Question 3 was flagged as NEEDS_REVIEW with CONTENT_MISMATCH_SUSPECTED
    prop = data["proposals"][0]
    assert prop["status"] == "needs_review"
    assert prop["rejection_reason"] == "CONTENT_MISMATCH_SUSPECTED"


def test_unapproved_ai_generated_reference_blocks_evaluation(client: TestClient, db_session: Session, diagnostic_env):
    """
    Verifies that when a question has an AI-generated reference answer (is_reference_proposed=True),
    evaluation is blocked until the teacher reviews and approves the reference key.
    """
    env = diagnostic_env
    sub = env["submission"]
    q1 = env["q1"]

    # Mark reference key as proposed
    q1.is_reference_proposed = True
    q1.reference_status = "proposed"
    db_session.commit()

    # Provide approved student answer with upload & extraction
    upload = AnswerSheetUpload(
        submission_id=sub.id,
        original_filename="sample_ans.pdf",
        stored_filename="sample_ans_uuid.pdf",
        storage_path="/tmp/sample_ans_uuid.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
        upload_status=UploadStatus.EXTRACTED.value,
    )
    db_session.add(upload)
    db_session.flush()

    extraction = OCRExtraction(
        upload_id=upload.id,
        provider_name="mock_ocr",
        processing_status=UploadStatus.EXTRACTED.value,
        extracted_text="6",
        confidence=0.95,
    )
    db_session.add(extraction)
    db_session.flush()

    qa = QuestionAnswer(
        submission_id=sub.id,
        question_id=q1.id,
        answer_text="6",
    )
    db_session.add(qa)
    db_session.flush()

    prop = ProposedAnswer(
        submission_id=sub.id,
        upload_id=upload.id,
        ocr_extraction_id=extraction.id,
        question_id=q1.id,
        proposed_text="6",
        status=ProposalStatus.APPROVED.value,
        confidence=0.95,
    )
    db_session.add(prop)
    db_session.flush()

    review = TeacherReview(
        proposal_id=prop.id,
        submission_id=sub.id,
        question_id=q1.id,
        reviewer_id=env["teacher"].id,
        action=ReviewAction.APPROVE.value,
        original_text="6",
        final_text="6",
    )
    db_session.add(review)
    db_session.commit()

    headers = auth_headers_for_user(env["teacher"])
    eval_resp = client.post(
        f"/api/v1/submissions/{sub.id}/questions/{q1.id}/evaluate",
        headers=headers,
    )
    assert eval_resp.status_code == 422
    err_body = eval_resp.json()
    err_msg = err_body.get("error", {}).get("message", "") or err_body.get("detail", "")
    assert "unapproved AI-proposed reference answer" in err_msg

    # Teacher approves the reference answer
    approve_resp = client.post(
        f"/api/v1/assessments/{env['assessment'].id}/questions/{q1.id}/approve-reference",
        json={"expected_answer": "5", "rubric": "Award 1 mark for exact 5."},
        headers=headers,
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["is_reference_proposed"] is False
    assert approve_resp.json()["reference_status"] == "approved"

    # Now evaluation succeeds
    eval_resp2 = client.post(
        f"/api/v1/submissions/{sub.id}/questions/{q1.id}/evaluate",
        headers=headers,
    )
    assert eval_resp2.status_code == 200
    res_data = eval_resp2.json()
    assert res_data["status"] == "completed"
    finding = res_data["findings"][0]
    assert finding["verdict"] == "incorrect"
    assert finding["error_amount"] == "+1"
    assert finding["correct_answer"] == "5"


def test_question_paper_parsing_and_generation(client: TestClient, db_session: Session, diagnostic_env):
    """
    Tests question paper text parsing, automatic proposal of reference solutions and rubrics,
    and bulk generation of reference keys.
    """
    from app.services.question_ingestion_service import question_ingestion_service

    sample_paper = """
    Question 1: Calculate 2 + 3 = ? [1 mark]
    Question 2: Define the derivative of f(x) = x^2. (5 marks)
    Question 3: State Newton's second law of motion. [10 marks]
    """

    parsed = question_ingestion_service.parse_question_blocks(sample_paper)
    assert len(parsed) == 3
    assert parsed[0]["question_number"] == 1
    assert parsed[0]["marks"] == 1.0
    assert "2 + 3" in parsed[0]["prompt"]

    assert parsed[1]["question_number"] == 2
    assert parsed[1]["marks"] == 5.0

    assert parsed[2]["question_number"] == 3
    assert parsed[2]["marks"] == 10.0

    # Test proposing reference answers
    ans1, rub1 = question_ingestion_service.propose_reference_solution(parsed[0]["prompt"], parsed[0]["question_type"])
    assert ans1 == "5"
    assert "2 + 3 = 5" in rub1

    ans2, rub2 = question_ingestion_service.propose_reference_solution(parsed[1]["prompt"], parsed[1]["question_type"])
    assert "2x" in ans2
    assert "power rule" in rub2

    ans3, rub3 = question_ingestion_service.propose_reference_solution(parsed[2]["prompt"], parsed[2]["question_type"])
    assert "F = m*a" in ans3

    # Test bulk generation endpoint
    env = diagnostic_env
    headers = auth_headers_for_user(env["teacher"])
    gen_resp = client.post(
        f"/api/v1/assessments/{env['assessment'].id}/generate-reference-keys",
        headers=headers,
    )
    assert gen_resp.status_code == 200
    qs = gen_resp.json()
    assert len(qs) >= 3
    for q in qs:
        assert q["is_reference_proposed"] is True
        assert q["reference_status"] == "proposed"
        assert q["expected_answer"] is not None
        assert q["rubric"] is not None

