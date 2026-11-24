"""Pydantic data schemas package."""

from app.models.enums import QuestionType, SubmissionStatus, UploadStatus, UserRole
from app.schemas.common import PaginatedResponse
from app.schemas.health import APIHealthResponse, HealthResponse
from app.schemas.user import (
    LoginRequest,
    Token,
    TokenData,
    UserBase,
    UserCreate,
    UserRead,
    UserRegister,
    UserUpdate,
)
from app.schemas.topic import LearningTopicBase, LearningTopicCreate, LearningTopicRead, LearningTopicUpdate
from app.schemas.assessment import AssessmentBase, AssessmentCreate, AssessmentRead, AssessmentUpdate
from app.schemas.question import QuestionBase, QuestionCreate, QuestionRead, QuestionUpdate
from app.schemas.submission import (
    QuestionAnswerBase,
    QuestionAnswerCreate,
    QuestionAnswerRead,
    QuestionAnswerUpdate,
    SubmissionBase,
    SubmissionCreate,
    SubmissionRead,
    SubmissionUpdate,
)
from app.schemas.upload import AnswerSheetUploadBase, AnswerSheetUploadRead
from app.schemas.ocr import (
    OCRExtractionRead,
    OCRExtractionSegment,
    OCRProcessTriggerResponse,
    ProcessingStatusRead,
)
from app.schemas.matching import (
    AnswerMatchingResponse,
    ProposedAnswerRead,
    ProposedAnswerReviewResponse,
    TeacherApproveRequest,
    TeacherCorrectRequest,
    TeacherRejectRequest,
    TeacherReviewRead,
    UnansweredQuestionInfo,
    UnmatchedSegmentInfo,
)
from app.schemas.inferred_qa import (
    InferredQAItem,
    InferredQAUpdateRequest,
    InferredQAResponse,
)
from app.schemas.evaluation import (
    EvaluationFindingRead,
    EvaluationRunDetailRead,
    EvaluationRunRead,
    FindingOutput,
    FindingReviewAuditRead,
    FindingReviewRequest,
    FindingReviewResponse,
    SubmissionEvaluationSummary,
)
from app.schemas.remediation import (
    PracticeItemOutput,
    PracticeItemReviewRequest,
    PracticeItemReviewResponse,
    RemediationGenerationSummary,
    RemediationItemAuditRead,
    RemediationItemStudentRead,
    RemediationItemTeacherRead,
    RemediationRunDetailRead,
    RemediationRunRead,
)
from app.schemas.outcome import (
    InterventionOutcomesSummary,
    StudentConceptProgressRead,
    StudentFollowupEvidenceRead,
    StudentProgressReportRead,
    TeacherFollowupEvidenceRead,
    TeacherInterventionOutcomeRead,
)
from app.schemas.review_queue import (
    PendingReviewItem,
    PendingReviewQueueResponse,
)
from app.schemas.cluster import (
    MisconceptionClusterItem,
    MisconceptionClusterResponse,
)

__all__ = [
    "PaginatedResponse",
    "HealthResponse",
    "APIHealthResponse",
    "UserRole",
    "QuestionType",
    "SubmissionStatus",
    "UploadStatus",
    "UserBase",
    "UserCreate",
    "UserRead",
    "UserUpdate",
    "LearningTopicBase",
    "LearningTopicCreate",
    "LearningTopicRead",
    "LearningTopicUpdate",
    "AssessmentBase",
    "AssessmentCreate",
    "AssessmentRead",
    "AssessmentUpdate",
    "QuestionBase",
    "QuestionCreate",
    "QuestionRead",
    "QuestionUpdate",
    "SubmissionBase",
    "SubmissionCreate",
    "SubmissionRead",
    "SubmissionUpdate",
    "QuestionAnswerBase",
    "QuestionAnswerCreate",
    "QuestionAnswerRead",
    "QuestionAnswerUpdate",
    "AnswerSheetUploadBase",
    "AnswerSheetUploadRead",
    "OCRExtractionRead",
    "OCRExtractionSegment",
    "OCRProcessTriggerResponse",
    "ProcessingStatusRead",
    "ProposedAnswerRead",
    "UnmatchedSegmentInfo",
    "UnansweredQuestionInfo",
    "AnswerMatchingResponse",
    "TeacherApproveRequest",
    "TeacherCorrectRequest",
    "TeacherRejectRequest",
    "TeacherReviewRead",
    "ProposedAnswerReviewResponse",
    "FindingOutput",
    "EvaluationFindingRead",
    "FindingReviewAuditRead",
    "EvaluationRunRead",
    "EvaluationRunDetailRead",
    "FindingReviewRequest",
    "FindingReviewResponse",
    "SubmissionEvaluationSummary",
    "PracticeItemOutput",
    "RemediationItemAuditRead",
    "RemediationItemTeacherRead",
    "RemediationItemStudentRead",
    "RemediationRunRead",
    "RemediationRunDetailRead",
    "PracticeItemReviewRequest",
    "PracticeItemReviewResponse",
    "RemediationGenerationSummary",
    "StudentFollowupEvidenceRead",
    "StudentConceptProgressRead",
    "StudentProgressReportRead",
    "TeacherFollowupEvidenceRead",
    "TeacherInterventionOutcomeRead",
    "InterventionOutcomesSummary",
    "PendingReviewItem",
    "PendingReviewQueueResponse",
    "MisconceptionClusterItem",
    "MisconceptionClusterResponse",
]



