from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_teacher
from app.core.database import get_db
from app.models.assessment import Assessment
from app.models.enums import SubmissionStatus, UserRole
from app.models.submission import Submission
from app.models.topic import LearningTopic
from app.models.user import User
from app.schemas.matching import (
    AnswerMatchingResponse,
    ProposedAnswerRead,
    ProposedAnswerReviewResponse,
    TeacherApproveRequest,
    TeacherCorrectRequest,
    TeacherRejectRequest,
)
from app.schemas.inferred_qa import InferredQAItem, InferredQAResponse, InferredQAUpdateRequest
from app.services.answer_sheet_inference_service import answer_sheet_inference_service
from app.services.matching_service import matching_service

router = APIRouter()


@router.post(
    "/answer-sheets/zero-qp-context",
    status_code=status.HTTP_201_CREATED,
    summary="Create isolated assessment and submission context for Answer-Sheet-Only mode",
    tags=["Matching & Inferred QA"],
)
def create_zero_qp_context(
    filename: Optional[str] = Query(None, description="Optional filename of answer sheet"),
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Creates an isolated pseudo-assessment and submission for Answer-Sheet-Only mode.
    Guarantees that older assessments or findings do not bleed into the current analysis.
    """
    topic = db.query(LearningTopic).filter(LearningTopic.name == "Computer Networks").first()
    if not topic:
        topic = LearningTopic(
            name="Computer Networks",
            description="Computer networking protocols, delays, architectures and subnetting",
        )
        db.add(topic)
        db.commit()
        db.refresh(topic)

    clean_name = filename or "Student Answer Sheet"
    # Create isolated pseudo-assessment
    assessment = Assessment(
        title=f"Zero-QP Assessment ({clean_name})",
        description=f"Isolated Zero-QP Assessment for {clean_name}",
        created_by=current_user.id,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    # Find or provision a student
    student = db.query(User).filter(User.role == UserRole.STUDENT.value).first()
    if not student:
        student = User(
            email="student_demo@learngraph.edu",
            full_name="Student Demo",
            role=UserRole.STUDENT.value,
            is_active=True,
        )
        db.add(student)
        db.commit()
        db.refresh(student)

    submission = Submission(
        assessment_id=assessment.id,
        student_id=student.id,
        status=SubmissionStatus.SUBMITTED.value,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    return {
        "assessment_id": assessment.id,
        "submission_id": submission.id,
        "assessment_title": assessment.title,
    }


@router.post(
    "/submissions/{submission_id}/match-answers",
    response_model=AnswerMatchingResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger deterministic answer-to-question matching for a submission",
)
def match_submission_answers(
    submission_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> AnswerMatchingResponse:
    """
    Deterministically matches OCR extracted segments to assessment questions for a submission.
    Teacher-only operation.
    """
    return matching_service.match_answers(db=db, submission_id=submission_id)


@router.post(
    "/answer-sheets/{upload_id}/match-answers",
    response_model=AnswerMatchingResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger deterministic answer-to-question matching for an answer sheet upload",
)
def match_upload_answers(
    upload_id: int,
    assessment_id: Optional[int] = Query(None, description="Optional target assessment ID to bind/match against"),
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> AnswerMatchingResponse:
    """
    Deterministically matches OCR segments from a specific upload to assessment questions.
    Teacher-only operation.
    """
    return matching_service.match_answers(db=db, upload_id=upload_id, assessment_id=assessment_id)


@router.get(
    "/submissions/{submission_id}/proposed-answers",
    response_model=AnswerMatchingResponse,
    status_code=status.HTTP_200_OK,
    summary="Get proposed answer matches and review status for a submission",
)
def get_submission_proposed_answers(
    submission_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> AnswerMatchingResponse:
    """
    Retrieves proposed matches, confidence signals, unmatched segments, and unanswered questions.
    Triggers matching automatically if not yet matched. Teacher-only operation.
    """
    return matching_service.get_submission_proposals(db=db, submission_id=submission_id)


@router.get(
    "/answer-sheets/{upload_id}/proposed-answers",
    response_model=AnswerMatchingResponse,
    status_code=status.HTTP_200_OK,
    summary="Get proposed answer matches for a specific answer sheet upload",
)
def get_upload_proposed_answers(
    upload_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> AnswerMatchingResponse:
    """
    Retrieves proposed matches for a specific answer sheet upload. Teacher-only operation.
    """
    return matching_service.get_upload_proposals(db=db, upload_id=upload_id)


@router.get(
    "/proposed-answers/{proposal_id}",
    response_model=ProposedAnswerRead,
    status_code=status.HTTP_200_OK,
    summary="Get a single proposed answer by ID",
)
def get_proposed_answer(
    proposal_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> ProposedAnswerRead:
    """
    Retrieves details for a single proposed answer. Teacher-only operation.
    """
    return matching_service.get_proposal(db=db, proposal_id=proposal_id)


@router.post(
    "/proposed-answers/{proposal_id}/approve",
    response_model=ProposedAnswerReviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Teacher approves a proposed answer",
)
def approve_proposed_answer(
    proposal_id: int,
    payload: TeacherApproveRequest,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> ProposedAnswerReviewResponse:
    """
    Teacher approves a proposed answer:
    - Writes proposed text to authoritative QuestionAnswer.answer_text
    - Records audit trail with reviewer identifier derived strictly from authenticated teacher
    """
    return matching_service.approve_proposal(
        db=db, proposal_id=proposal_id, reviewer_id=current_user.id, request=payload
    )


@router.post(
    "/proposed-answers/{proposal_id}/correct",
    response_model=ProposedAnswerReviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Teacher corrects answer text and approves",
)
def correct_proposed_answer(
    proposal_id: int,
    payload: TeacherCorrectRequest,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> ProposedAnswerReviewResponse:
    """
    Teacher corrects answer text and approves:
    - Writes corrected text to authoritative QuestionAnswer.answer_text
    - Preserves original OCR proposed text in the proposal and audit record
    - Records audit trail with reviewer identifier derived strictly from authenticated teacher
    """
    return matching_service.correct_proposal(
        db=db, proposal_id=proposal_id, reviewer_id=current_user.id, request=payload
    )


@router.post(
    "/proposed-answers/{proposal_id}/reject",
    response_model=ProposedAnswerReviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Teacher rejects a proposed answer",
)
def reject_proposed_answer(
    proposal_id: int,
    payload: TeacherRejectRequest,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> ProposedAnswerReviewResponse:
    """
    Teacher rejects a proposed answer:
    - Sets proposal status to rejected
    - Does NOT modify authoritative QuestionAnswer.answer_text
    - Records audit trail with reviewer identifier derived strictly from authenticated teacher
    """
    return matching_service.reject_proposal(
        db=db, proposal_id=proposal_id, reviewer_id=current_user.id, request=payload
    )


@router.post(
    "/answer-sheets/{upload_id}/infer-questions",
    response_model=InferredQAResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger Answer-Sheet-Only question inference and diagnostic evaluation",
    tags=["Matching & Inferred QA"],
)
async def infer_questions_from_answer_sheet(
    upload_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> InferredQAResponse:
    """
    Answer-Sheet-Only Mode:
    Infers distinct questions directly from student answers when no question paper is provided.
    Evaluates understanding based on domain knowledge, creates clean question-answer entities,
    and removes 300+ unnumbered segment clutter.
    """
    return await answer_sheet_inference_service.infer_questions_from_answer_sheet(
        db=db, upload_id=upload_id, current_user=current_user
    )


@router.patch(
    "/answer-sheets/{upload_id}/inferred-questions/{question_id}",
    response_model=InferredQAItem,
    status_code=status.HTTP_200_OK,
    summary="Teacher edits an AI-inferred question prompt or expected solution",
    tags=["Matching & Inferred QA"],
)
async def update_inferred_question(
    upload_id: int,
    question_id: int,
    payload: InferredQAUpdateRequest,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> InferredQAItem:
    """
    Allows a teacher to edit an inferred question if the AI inferred the prompt imperfectly.
    """
    return await answer_sheet_inference_service.update_inferred_question(
        db=db, upload_id=upload_id, question_id=question_id, data=payload, current_user=current_user
    )
