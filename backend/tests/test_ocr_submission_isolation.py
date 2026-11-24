import pytest
from app.models.enums import ProposalStatus, QuestionType, UserRole
from app.models.user import User
from app.models.topic import LearningTopic
from app.models.assessment import Assessment, Question
from app.models.submission import Submission, AnswerSheetUpload
from app.models.ocr import OCRExtraction
from app.models.matching import ProposedAnswer
from app.services.matching_service import matching_service


def test_extract_question_number_does_not_match_ip_or_float():
    """Verify IP addresses and floating-point numbers are not mistaken for question numbers."""
    ip_seg = {"text": "Fourlpaddress 203.165.100.8 and mask=255.255.255.240"}
    q_num, text = matching_service.extract_question_number(ip_seg)
    assert q_num is None, f"Expected None for IP address but got {q_num}"

    float_seg = {"text": "Jinkspeedx 0.1sec link speed = 80x10^2 bps"}
    q_num, text = matching_service.extract_question_number(float_seg)
    assert q_num is None, f"Expected None for float but got {q_num}"

    # Valid question labels must still match
    q1_seg = {"text": "Question 1: Frame size is 1000 bytes"}
    q_num, text = matching_service.extract_question_number(q1_seg)
    assert q_num == 1
    assert "Frame size is 1000 bytes" in text

    q2_seg = {"text": "2. Subnetting calculations"}
    q_num, text = matching_service.extract_question_number(q2_seg)
    assert q_num == 2


def test_check_content_mismatch_flags_computer_networks_vs_math(db_session):
    """Verify Computer Networks student content is detected as a mismatch against Math/Linear Algebra."""
    math_q = Question(
        assessment_id=1,
        topic_id=1,
        prompt="Is the identity matrix invertible?",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=5.0,
        expected_answer="Yes, det(I) = 1 != 0",
        rubric="Full credit for verifying determinant is non-zero",
    )

    cn_answer_text = "Distance vector routing algorithm uses Bellman-Ford equation Dx(y) = min { c(x,v) + Dv(y) }"
    reason = matching_service.check_content_mismatch(cn_answer_text, math_q, [math_q])
    assert reason == "CONTENT_MISMATCH_SUSPECTED"

    math_answer_text = "The identity matrix is invertible because its determinant equals 1"
    reason_math = matching_service.check_content_mismatch(math_answer_text, math_q, [math_q])
    assert reason_math is None


def test_upload_isolation_prevents_mock_leak_between_uploads(db_session):
    """
    Verifies that proposals belonging to an older mock upload never leak into a new upload,
    guaranteeing strict submission and upload isolation.
    """
    teacher = User(
        email="teacher_iso@test.com",
        full_name="Teacher Iso",
        hashed_password="pw",
        role=UserRole.TEACHER.value,
    )
    student = User(
        email="student_iso@test.com",
        full_name="Student Iso",
        hashed_password="pw",
        role=UserRole.STUDENT.value,
    )
    topic = LearningTopic(name="Math Topic", description="Linear Algebra")
    db_session.add_all([teacher, student, topic])
    db_session.flush()

    assessment = Assessment(
        title="Linear Algebra Quiz",
        description="Matrices",
        created_by=teacher.id,
    )
    db_session.add(assessment)
    db_session.flush()

    q1 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Is the identity matrix invertible?",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=5.0,
        expected_answer="Yes",
    )
    db_session.add(q1)
    db_session.flush()

    # Submission 1 with old mock upload
    sub1 = Submission(assessment_id=assessment.id, student_id=student.id)
    db_session.add(sub1)
    db_session.flush()

    old_upload = AnswerSheetUpload(
        submission_id=sub1.id,
        original_filename="old_mock.pdf",
        stored_filename="old_mock_stored.pdf",
        storage_path="/tmp/old_mock.pdf",
        content_type="application/pdf",
        file_size_bytes=500,
        upload_status="extracted",
    )
    db_session.add(old_upload)
    db_session.flush()

    old_extraction = OCRExtraction(
        upload_id=old_upload.id,
        extracted_text="The derivative of f(x) = x^2 is f'(x) = 2x.",
        structured_segments=[
            {"segment_id": 1, "page": 1, "text": "The derivative of f(x) = x^2 is f'(x) = 2x.", "confidence": 0.95}
        ],
        confidence=0.95,
        provider_name="mock_ocr_provider",
        processing_status="extracted",
    )
    db_session.add(old_extraction)
    db_session.flush()

    old_proposal = ProposedAnswer(
        submission_id=sub1.id,
        upload_id=old_upload.id,
        ocr_extraction_id=old_extraction.id,
        question_id=q1.id,
        segment_id=1,
        proposed_text="The derivative of f(x) = x^2 is f'(x) = 2x.",
        confidence=0.95,
        status=ProposalStatus.APPROVED.value,
    )
    db_session.add(old_proposal)
    db_session.flush()

    # Now create a brand new upload (Upload 2) for Submission 1 with real Computer Networks text
    new_upload = AnswerSheetUpload(
        submission_id=sub1.id,
        original_filename="real_exam.pdf",
        stored_filename="real_exam_stored.pdf",
        storage_path="/tmp/real_exam.pdf",
        content_type="application/pdf",
        file_size_bytes=3000000,
        upload_status="extracted",
    )
    db_session.add(new_upload)
    db_session.flush()

    new_extraction = OCRExtraction(
        upload_id=new_upload.id,
        extracted_text="Distance vector routing algorithm with routing tables",
        structured_segments=[
            {"segment_id": 1, "page": 1, "text": "Question 1: Distance vector routing algorithm with routing tables", "confidence": 0.92}
        ],
        confidence=0.92,
        provider_name="paddleocr",
        processing_status="extracted",
    )
    db_session.add(new_extraction)
    db_session.flush()

    # Query proposals for the submission - MUST match latest upload (new_upload) and NEVER return old mock proposal
    sub_res = matching_service.get_submission_proposals(db=db_session, submission_id=sub1.id)
    assert sub_res.upload_id == new_upload.id
    for p in sub_res.proposals:
        assert "derivative" not in p.proposed_text, "Old mock text leaked into submission proposals!"
        assert "Newton" not in p.proposed_text, "Old mock text leaked into submission proposals!"

    # Query proposals directly for new_upload
    upload_res = matching_service.get_upload_proposals(db=db_session, upload_id=new_upload.id)
    assert upload_res.upload_id == new_upload.id
    for p in upload_res.proposals:
        assert "derivative" not in p.proposed_text, "Old mock text leaked into upload proposals!"
        assert "Newton" not in p.proposed_text, "Old mock text leaked into upload proposals!"


def test_rebind_upload_to_subject_assessment(db_session):
    """
    Verifies that when an upload is re-matched with an assessment_id corresponding to
    its actual subject, the upload is safely re-bound and cleanly matched.
    """
    teacher = User(
        email="teacher_rb@test.com",
        full_name="Teacher Rb",
        hashed_password="pw",
        role=UserRole.TEACHER.value,
    )
    student = User(
        email="student_rb@test.com",
        full_name="Student Rb",
        hashed_password="pw",
        role=UserRole.STUDENT.value,
    )
    math_topic = LearningTopic(name="Math Topic", description="Linear Algebra")
    cn_topic = LearningTopic(name="Computer Networks", description="Routing & Networking")
    db_session.add_all([teacher, student, math_topic, cn_topic])
    db_session.flush()

    math_assessment = Assessment(title="Matrix Quiz", description="Math", created_by=teacher.id)
    cn_assessment = Assessment(title="Computer Networks Exam", description="CN", created_by=teacher.id)
    db_session.add_all([math_assessment, cn_assessment])
    db_session.flush()

    # Questions for CN assessment
    cn_q1 = Question(
        assessment_id=cn_assessment.id,
        topic_id=cn_topic.id,
        prompt="Explain Distance Vector Routing and the Bellman-Ford equation.",
        question_type=QuestionType.ESSAY.value,
        marks=5.0,
        expected_answer="Distance vector routing algorithm uses Bellman-Ford",
    )
    db_session.add(cn_q1)
    db_session.flush()

    # Upload initially attached to math assessment
    sub_math = Submission(assessment_id=math_assessment.id, student_id=student.id)
    db_session.add(sub_math)
    db_session.flush()

    upload = AnswerSheetUpload(
        submission_id=sub_math.id,
        original_filename="cn_test.pdf",
        stored_filename="cn_test_stored.pdf",
        storage_path="/tmp/cn_test.pdf",
        content_type="application/pdf",
        file_size_bytes=100000,
        upload_status="extracted",
    )
    db_session.add(upload)
    db_session.flush()

    ext = OCRExtraction(
        upload_id=upload.id,
        extracted_text="Distance Vector Routing Bellman-Ford",
        structured_segments=[
            {"segment_id": 1, "page": 1, "text": "Question 1: Distance Vector Routing Bellman-Ford", "confidence": 0.94}
        ],
        confidence=0.94,
        provider_name="paddleocr",
        processing_status="extracted",
    )
    db_session.add(ext)
    db_session.flush()

    # Re-match with cn_assessment.id
    match_res = matching_service.match_answers(
        db=db_session,
        upload_id=upload.id,
        assessment_id=cn_assessment.id,
    )

    assert match_res.assessment_id == cn_assessment.id
    assert match_res.matched_count == 1
    assert match_res.proposals[0].question_id == cn_q1.id
    assert match_res.proposals[0].status == ProposalStatus.PROPOSED.value
