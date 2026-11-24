"""SQLAlchemy models and metadata package."""

from app.core.database import Base
from app.models.enums import (
    EvaluationStatus,
    FindingCategory,
    FindingReviewAction,
    FindingReviewStatus,
    InvalidStateTransitionError,
    PracticeItemReviewAction,
    PracticeItemReviewStatus,
    PracticeQuestionType,
    ProposalStatus,
    QuestionType,
    RemediationRunStatus,
    ReviewAction,
    SubmissionStatus,
    UploadStatus,
    UserRole,
    FollowUpQuestionType,
    FollowUpStatus,
    CorrectionFieldName,
    CorrectionStatus,
    validate_finding_review_transition,
    validate_practice_item_transition,
    validate_proposal_transition,
    validate_upload_transition,
)
from app.models.user import User
from app.models.topic import LearningTopic
from app.models.assessment import Assessment, Question
from app.models.submission import AnswerSheetUpload, QuestionAnswer, Submission
from app.models.ocr import OCRExtraction
from app.models.matching import ProposedAnswer, TeacherReview
from app.models.evaluation import EvaluationFinding, EvaluationRun, FindingReviewAudit
from app.models.follow_up import FollowUpQuestion
from app.models.correction import FindingCorrection
from app.models.remediation import RemediationItem, RemediationItemAudit, RemediationRun
from app.models.practice import PracticeResponse, PracticeSession
from app.models.enums import PracticeSessionStatus, validate_practice_session_transition

__all__ = [
    "Base",
    "UserRole",
    "QuestionType",
    "SubmissionStatus",
    "UploadStatus",
    "ProposalStatus",
    "ReviewAction",
    "EvaluationStatus",
    "FindingCategory",
    "FindingReviewStatus",
    "FindingReviewAction",
    "RemediationRunStatus",
    "FollowUpQuestionType",
    "FollowUpStatus",
    "CorrectionFieldName",
    "CorrectionStatus",
    "PracticeQuestionType",
    "PracticeItemReviewStatus",
    "PracticeItemReviewAction",
    "InvalidStateTransitionError",
    "validate_upload_transition",
    "validate_proposal_transition",
    "validate_finding_review_transition",
    "validate_practice_item_transition",
    "User",
    "LearningTopic",
    "Assessment",
    "Question",
    "Submission",
    "QuestionAnswer",
    "AnswerSheetUpload",
    "OCRExtraction",
    "ProposedAnswer",
    "TeacherReview",
    "EvaluationRun",
    "EvaluationFinding",
    "FindingReviewAudit",
    "FollowUpQuestion",
    "FindingCorrection",
    "RemediationRun",
    "RemediationItem",
    "RemediationItemAudit",
    "PracticeSessionStatus",
    "validate_practice_session_transition",
    "PracticeSession",
    "PracticeResponse",
]



