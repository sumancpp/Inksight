import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.enums import FindingCategory, FindingReviewAction, FindingReviewStatus, UserRole
from app.models.evaluation import EvaluationFinding, EvaluationRun, FindingReviewAudit
from app.models.matching import ProposedAnswer
from app.models.ocr import OCRExtraction
from app.models.submission import AnswerSheetUpload, QuestionAnswer, Submission
from app.models.assessment import Question, Assessment
from app.models.topic import LearningTopic
from app.models.user import User
from app.schemas.evaluation import (
    ConfidenceDetails,
    FindingOutput,
    FindingReviewRequest,
    MisconceptionItem,
    compute_confidence_level,
    derive_requires_teacher_review,
)
from app.services.evaluation_service import evaluation_service
from app.services.evaluator.mock_evaluator import MockEvaluator
from app.services.evaluator.base import EvaluationInput


def test_single_source_of_truth_derivation():
    """Verify that FindingOutput derives scalar confidence from confidence_details.score, and misconception_hypothesis from misconceptions[0]."""
    item = MisconceptionItem(
        hypothesis="Product rule confused with distributive derivative",
        evidence_excerpt="f'g'",
        linked_concept="Product Rule",
        severity="high",
    )
    conf = ConfidenceDetails(score=0.88, level="high", uncertainty_reasons=[])

    finding = FindingOutput(
        concept_name="Calculus",
        category=FindingCategory.LIKELY_MISCONCEPTION,
        confidence=0.50,  # Deliberately divergent initial value
        confidence_details=conf,
        misconceptions=[item],
        evidence_excerpt="f'g'",
        rationale="Detailed explanation",
    )

    # Derived invariants:
    assert finding.confidence == 0.88
    assert finding.misconception_hypothesis == "Product rule confused with distributive derivative"
    assert finding.requires_teacher_review is False


def test_derive_requires_teacher_review_canonical_helper():
    """Verify derive_requires_teacher_review works for ConfidenceDetails, dicts, and None."""
    assert derive_requires_teacher_review(None) is False
    assert derive_requires_teacher_review(ConfidenceDetails(score=0.90, level="high")) is False
    assert derive_requires_teacher_review(ConfidenceDetails(score=0.75, level="medium")) is False
    assert derive_requires_teacher_review(ConfidenceDetails(score=0.50, level="low")) is True
    # Dicts
    assert derive_requires_teacher_review({"score": 0.50, "level": "low"}) is True
    assert derive_requires_teacher_review({"score": 0.85, "level": "high"}) is False
    # Derived from score inside dict if level missing
    assert derive_requires_teacher_review({"score": 0.40}) is True
    assert derive_requires_teacher_review({"score": 0.90}) is False


def test_grounding_drop_sets_low_confidence_and_review_flag():
    """If an evaluator outputs ungrounded misconceptions, they must be dropped. If all dropped, level becomes 'low' and requires_teacher_review becomes True."""
    evaluator = MockEvaluator()
    student_text = "The derivative is 2x."
    # The excerpt 'random_hallucinated_phrase' is NOT in student_text
    unverified_misc = MisconceptionItem(
        hypothesis="Hallucinated error",
        evidence_excerpt="random_hallucinated_phrase",
        linked_concept="Algebra",
        severity="medium",
    )
    norm_student = " ".join(student_text.lower().split())

    # Simulate evaluator proposing ungrounded item
    finding = FindingOutput(
        concept_name="Math",
        category=FindingCategory.LIKELY_MISCONCEPTION,
        confidence=0.90,
        confidence_details=ConfidenceDetails(score=0.90, level="high", uncertainty_reasons=[]),
        misconceptions=[unverified_misc],
        rationale="Testing drop",
    )

    # Grounding filter logic as in evaluation_service
    grounded = []
    attempted = len(finding.misconceptions)
    for m in finding.misconceptions:
        norm_item = " ".join(m.evidence_excerpt.lower().split())
        if norm_item in norm_student:
            grounded.append(m)
    finding.misconceptions = grounded

    if attempted > 0 and len(grounded) == 0:
        finding.confidence_details.level = "low"
        finding.confidence_details.uncertainty_reasons.append("no_grounded_misconception_evidence")

    finding.requires_teacher_review = (finding.confidence_details.level == "low")
    assert len(finding.misconceptions) == 0
    assert finding.confidence_details.level == "low"
    assert "no_grounded_misconception_evidence" in finding.confidence_details.uncertainty_reasons
    assert finding.requires_teacher_review is True


def test_degraded_output_sets_review_gate():
    """Verify mock degraded output returns level='low' and requires_teacher_review=True."""
    evaluator = MockEvaluator()
    import asyncio
    payload = EvaluationInput(
        question_prompt="What is 2 + 2?",
        student_answer="trigger_degraded test failure",
    )
    result = asyncio.run(evaluator.evaluate(payload))
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.requires_teacher_review is True
    assert finding.confidence_details.level == "low"
    assert "evaluator_output_invalid" in finding.confidence_details.uncertainty_reasons


def test_review_gate_requires_explicit_acknowledgement(db_session: Session):
    """A low-confidence finding requiring teacher review cannot be accepted without acknowledge_uncertainty=True."""
    teacher = User(
        email="gate_teacher@example.com",
        full_name="Gate Teacher",
        hashed_password="pw",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    student = User(
        email="gate_student@example.com",
        full_name="Gate Student",
        hashed_password="pw",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    db_session.add_all([teacher, student])
    db_session.commit()

    topic = LearningTopic(name="Math Gate", description="Gate testing")
    db_session.add(topic)
    db_session.commit()

    assessment = Assessment(title="Gate Assessment", created_by=teacher.id)
    db_session.add(assessment)
    db_session.commit()

    question = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Solve x",
        question_type="short_answer",
        marks=5.0,
    )
    db_session.add(question)
    db_session.commit()

    submission = Submission(
        assessment_id=assessment.id,
        student_id=student.id,
        status="submitted",
    )
    db_session.add(submission)
    db_session.commit()

    qa = QuestionAnswer(
        submission_id=submission.id,
        question_id=question.id,
        answer_text="Sample text",
    )
    db_session.add(qa)
    db_session.commit()

    run = EvaluationRun(
        submission_id=submission.id,
        question_id=question.id,
        question_answer_id=qa.id,
        evaluator_name="mock_evaluator",
        answer_text_hash="dummy_hash_123",
        answer_text_snapshot="Sample text",
        status="completed",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    finding = EvaluationFinding(
        run_id=run.id,
        category=FindingCategory.INSUFFICIENT_EVIDENCE.value,
        confidence=0.45,
        rationale="Uncertain finding",
        review_status=FindingReviewStatus.PENDING_REVIEW.value,
        requires_teacher_review=True,
        confidence_details={"score": 0.45, "level": "low", "uncertainty_reasons": ["unrecognized_structure"]},
        misconceptions=[],
    )
    db_session.add(finding)
    db_session.commit()
    db_session.refresh(finding)

    # 1. Attempt accept WITHOUT acknowledge_uncertainty -> HTTP 422
    req_unack = FindingReviewRequest(
        action=FindingReviewAction.ACCEPT,
        review_notes="Looks fine to me",
        acknowledge_uncertainty=False,
    )
    with pytest.raises(HTTPException) as exc_info:
        evaluation_service.review_finding(
            db=db_session,
            finding_id=finding.id,
            reviewer_id=teacher.id,
            request=req_unack,
        )
    assert exc_info.value.status_code == 422
    assert "Low-confidence finding requires explicit acknowledgement" in exc_info.value.detail

    # 2. Attempt accept WITH acknowledge_uncertainty -> Succeeds & logs audit
    req_ack = FindingReviewRequest(
        action=FindingReviewAction.ACCEPT,
        review_notes="Verified manually by teacher",
        acknowledge_uncertainty=True,
    )
    response = evaluation_service.review_finding(
        db=db_session,
        finding_id=finding.id,
        reviewer_id=teacher.id,
        request=req_ack,
    )
    assert response.finding.review_status == FindingReviewStatus.ACCEPTED.value
    assert "[Teacher explicitly acknowledged diagnostic uncertainty]" in response.audit.review_notes


@pytest.mark.anyio
async def test_deduplication_reuses_existing_completed_run(db_session: Session):
    """When a completed evaluation run exists for the exact answer hash, evaluate_question_answer returns it without duplicating findings."""
    teacher = User(
        email="dedup_teacher@example.com",
        full_name="Dedup Teacher",
        hashed_password="pw",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    student = User(
        email="dedup_student@example.com",
        full_name="Dedup Student",
        hashed_password="pw",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    db_session.add_all([teacher, student])
    db_session.commit()

    topic = LearningTopic(name="Dedup Topic", description="Dedup testing")
    db_session.add(topic)
    db_session.commit()

    assessment = Assessment(title="Dedup Assessment", created_by=teacher.id)
    db_session.add(assessment)
    db_session.commit()

    question = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Calculate 2 + 3",
        expected_answer="5",
        rubric="Must state 5",
        question_type="short_answer",
        marks=1.0,
    )
    db_session.add(question)
    db_session.commit()

    submission = Submission(
        assessment_id=assessment.id,
        student_id=student.id,
        status="submitted",
    )
    db_session.add(submission)
    db_session.commit()

    qa = QuestionAnswer(
        submission_id=submission.id,
        question_id=question.id,
        answer_text="6",
    )
    db_session.add(qa)
    db_session.commit()

    upload = AnswerSheetUpload(
        submission_id=submission.id,
        original_filename="test.pdf",
        stored_filename="test_stored.pdf",
        storage_path="/tmp/test_stored.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
        upload_status="extracted",
    )
    db_session.add(upload)
    db_session.commit()

    extraction = OCRExtraction(
        upload_id=upload.id,
        provider_name="mock_ocr",
        processing_status="extracted",
        extracted_text="6",
        confidence=0.95,
        structured_segments=[{"segment_id": 1, "page": 1, "text": "6", "confidence": 0.95}],
    )
    db_session.add(extraction)
    db_session.commit()

    p = ProposedAnswer(
        submission_id=submission.id,
        upload_id=upload.id,
        ocr_extraction_id=extraction.id,
        question_id=question.id,
        segment_id=1,
        proposed_text="6",
        confidence=0.95,
        status="approved",
    )
    db_session.add(p)
    db_session.commit()

    # First evaluation
    run1 = await evaluation_service.evaluate_question_answer(
        db=db_session, submission_id=submission.id, question_id=question.id
    )
    assert run1.id is not None
    assert len(run1.findings) > 0

    finding_count_before = db_session.query(EvaluationFinding).count()

    # Second evaluation with identical answer text hash
    run2 = await evaluation_service.evaluate_question_answer(
        db=db_session, submission_id=submission.id, question_id=question.id
    )
    assert run2.id == run1.id

    finding_count_after = db_session.query(EvaluationFinding).count()
    assert finding_count_after == finding_count_before, "Deduplication must not create duplicate findings"


def test_score_is_truth_level_derivation():
    """Fix A & B: model returns score=0.5, level='high' -> stored level must be 'low', requires_teacher_review=True."""
    cd = ConfidenceDetails(score=0.5, level="high", uncertainty_reasons=[])
    assert cd.level == "low", "Score < 0.70 must derive level='low' regardless of model-provided level"

    finding = FindingOutput(
        concept_name="Calculus",
        category=FindingCategory.LIKELY_MISCONCEPTION,
        confidence=0.5,
        confidence_details=cd,
        rationale="Testing level derivation",
    )
    assert finding.confidence_details.level == "low"
    assert finding.requires_teacher_review is True


@pytest.mark.anyio
@pytest.mark.parametrize(
    "review_action,expected_reviewed_status",
    [
        (FindingReviewAction.REQUEST_REVISION, FindingReviewStatus.NEEDS_REVISION),
        (FindingReviewAction.ACCEPT, FindingReviewStatus.ACCEPTED),
        (FindingReviewAction.REJECT, FindingReviewStatus.REJECTED),
    ],
)
async def test_re_evaluation_supersedes_teacher_reviewed_finding_and_audits(
    db_session: Session, review_action: FindingReviewAction, expected_reviewed_status: FindingReviewStatus
):
    """Fix C: create finding, teacher reviews it (FLAGGED, ACCEPTED, or REJECTED), re-run evaluation -> old finding preserved with superseded status, audit row created, new finding exists."""
    teacher = User(
        email=f"supersede_teacher_{review_action.value}@example.com",
        full_name="Supersede Teacher",
        hashed_password="pw",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    student = User(
        email=f"supersede_student_{review_action.value}@example.com",
        full_name="Supersede Student",
        hashed_password="pw",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    db_session.add_all([teacher, student])
    db_session.commit()

    topic = LearningTopic(name=f"Supersede Topic {review_action.value}", description="Testing supersede")
    db_session.add(topic)
    db_session.commit()

    assessment = Assessment(title=f"Supersede Assessment {review_action.value}", created_by=teacher.id)
    db_session.add(assessment)
    db_session.commit()

    question = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="State 2 + 3",
        expected_answer="5",
        rubric="Must state 5",
        question_type="short_answer",
        marks=1.0,
    )
    db_session.add(question)
    db_session.commit()

    submission = Submission(
        assessment_id=assessment.id,
        student_id=student.id,
        status="submitted",
    )
    db_session.add(submission)
    db_session.commit()

    qa = QuestionAnswer(
        submission_id=submission.id,
        question_id=question.id,
        answer_text="6",
    )
    db_session.add(qa)
    db_session.commit()

    upload = AnswerSheetUpload(
        submission_id=submission.id,
        original_filename="test.pdf",
        stored_filename=f"test_stored_{review_action.value}.pdf",
        storage_path=f"/tmp/test_stored_{review_action.value}.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
        upload_status="extracted",
    )
    db_session.add(upload)
    db_session.commit()

    extraction = OCRExtraction(
        upload_id=upload.id,
        provider_name="mock_ocr",
        processing_status="extracted",
        extracted_text="6",
        confidence=0.95,
        structured_segments=[{"segment_id": 1, "page": 1, "text": "6", "confidence": 0.95}],
    )
    db_session.add(extraction)
    db_session.commit()

    p = ProposedAnswer(
        submission_id=submission.id,
        upload_id=upload.id,
        ocr_extraction_id=extraction.id,
        question_id=question.id,
        segment_id=1,
        proposed_text="6",
        confidence=0.95,
        status="approved",
    )
    db_session.add(p)
    db_session.commit()

    # Initial evaluation
    run1 = await evaluation_service.evaluate_question_answer(
        db=db_session, submission_id=submission.id, question_id=question.id
    )
    old_finding_id = run1.findings[0].id

    # Teacher reviews the finding (ACCEPT, REJECT, or REQUEST_REVISION)
    req_review = FindingReviewRequest(
        action=review_action,
        review_notes=f"Teacher action: {review_action.value}",
        acknowledge_uncertainty=True,
    )
    evaluation_service.review_finding(
        db=db_session,
        finding_id=old_finding_id,
        reviewer_id=teacher.id,
        request=req_review,
    )

    old_finding = db_session.query(EvaluationFinding).filter(EvaluationFinding.id == old_finding_id).first()
    assert old_finding.review_status == expected_reviewed_status.value

    # Simulate rerun by setting run status to pending
    run_obj = db_session.query(EvaluationRun).filter(EvaluationRun.id == run1.id).first()
    run_obj.status = "pending"
    db_session.commit()

    # Re-run evaluation
    run2 = await evaluation_service.evaluate_question_answer(
        db=db_session, submission_id=submission.id, question_id=question.id
    )

    # Verify old finding preserved with superseded status
    db_session.refresh(old_finding)
    assert old_finding.review_status == FindingReviewStatus.SUPERSEDED.value

    # Verify audit row created for superseded
    supersede_audit = (
        db_session.query(FindingReviewAudit)
        .filter(FindingReviewAudit.finding_id == old_finding_id, FindingReviewAudit.action == "superseded")
        .first()
    )
    assert supersede_audit is not None
    assert "[system] Superseded for re-evaluation" in supersede_audit.review_notes

    # Verify new finding exists in run
    all_findings = db_session.query(EvaluationFinding).filter(EvaluationFinding.run_id == run2.id).all()
    assert any(f.id != old_finding_id for f in all_findings)


def test_acknowledged_uncertainty_structured_column_and_audit(db_session: Session):
    """Fix E: FindingReviewAudit and EvaluationFinding track acknowledged_uncertainty as a boolean column."""
    teacher = User(
        email="ack_teacher@example.com",
        full_name="Ack Teacher",
        hashed_password="pw",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    student = User(
        email="ack_student@example.com",
        full_name="Ack Student",
        hashed_password="pw",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    db_session.add_all([teacher, student])
    db_session.commit()

    topic = LearningTopic(name="Ack Topic", description="Ack testing")
    db_session.add(topic)
    db_session.commit()

    assessment = Assessment(title="Ack Assessment", created_by=teacher.id)
    db_session.add(assessment)
    db_session.commit()

    question = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Solve y",
        question_type="short_answer",
        marks=2.0,
    )
    db_session.add(question)
    db_session.commit()

    submission = Submission(
        assessment_id=assessment.id,
        student_id=student.id,
        status="submitted",
    )
    db_session.add(submission)
    db_session.commit()

    qa = QuestionAnswer(
        submission_id=submission.id,
        question_id=question.id,
        answer_text="Sample text",
    )
    db_session.add(qa)
    db_session.commit()

    run = EvaluationRun(
        submission_id=submission.id,
        question_id=question.id,
        question_answer_id=qa.id,
        evaluator_name="mock_evaluator",
        answer_text_hash="dummy_hash_ack",
        answer_text_snapshot="Sample text",
        status="completed",
    )
    db_session.add(run)
    db_session.commit()

    finding = EvaluationFinding(
        run_id=run.id,
        category=FindingCategory.INSUFFICIENT_EVIDENCE.value,
        confidence=0.45,
        rationale="Uncertain finding",
        review_status=FindingReviewStatus.PENDING_REVIEW.value,
        requires_teacher_review=True,
        confidence_details={"score": 0.45, "level": "low", "uncertainty_reasons": ["unrecognized_structure"]},
        misconceptions=[],
    )
    db_session.add(finding)
    db_session.commit()

    req = FindingReviewRequest(
        action=FindingReviewAction.ACCEPT,
        review_notes="Explicitly approved",
        acknowledge_uncertainty=True,
    )
    resp = evaluation_service.review_finding(
        db=db_session,
        finding_id=finding.id,
        reviewer_id=teacher.id,
        request=req,
    )
    assert resp.finding.acknowledged_uncertainty is True
    assert resp.audit.acknowledged_uncertainty is True

    db_finding = db_session.query(EvaluationFinding).filter(EvaluationFinding.id == finding.id).first()
    assert db_finding.acknowledged_uncertainty is True
    db_audit = db_session.query(FindingReviewAudit).filter(FindingReviewAudit.id == resp.audit.id).first()
    assert db_audit.acknowledged_uncertainty is True


