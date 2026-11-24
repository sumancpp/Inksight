import enum
from typing import Set


class UserRole(str, enum.Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class QuestionType(str, enum.Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    SHORT_ANSWER = "short_answer"
    NUMERICAL = "numerical"
    ESSAY = "essay"


class SubmissionStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    REVIEWED = "reviewed"


class UploadStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    # Legacy / review states for backward compatibility
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal upload processing state transition is attempted."""
    pass


VALID_UPLOAD_TRANSITIONS: dict[UploadStatus, Set[UploadStatus]] = {
    UploadStatus.UPLOADED: {UploadStatus.QUEUED, UploadStatus.PROCESSING, UploadStatus.FAILED},
    UploadStatus.QUEUED: {UploadStatus.PROCESSING, UploadStatus.FAILED},
    UploadStatus.PROCESSING: {UploadStatus.EXTRACTED, UploadStatus.NEEDS_REVIEW, UploadStatus.FAILED, UploadStatus.QUEUED},
    UploadStatus.EXTRACTED: {UploadStatus.QUEUED, UploadStatus.NEEDS_REVIEW},
    UploadStatus.NEEDS_REVIEW: {UploadStatus.QUEUED, UploadStatus.EXTRACTED},
    UploadStatus.FAILED: {UploadStatus.QUEUED},
    UploadStatus.PENDING_REVIEW: {UploadStatus.QUEUED, UploadStatus.EXTRACTED, UploadStatus.REJECTED},
    UploadStatus.REJECTED: {UploadStatus.QUEUED},
}


def validate_upload_transition(current: str | UploadStatus, target: str | UploadStatus) -> None:
    current_status = UploadStatus(current) if isinstance(current, str) else current
    target_status = UploadStatus(target) if isinstance(target, str) else target

    if current_status == target_status:
        return

    allowed = VALID_UPLOAD_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise InvalidStateTransitionError(
            f"Invalid upload state transition from '{current_status.value}' to '{target_status.value}'."
        )


class ProposalStatus(str, enum.Enum):
    PROPOSED = "proposed"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    UNMATCHED = "unmatched"


class ReviewAction(str, enum.Enum):
    APPROVE = "approved"
    CORRECT = "corrected"
    REJECT = "rejected"


VALID_PROPOSAL_TRANSITIONS: dict[ProposalStatus, Set[ProposalStatus]] = {
    ProposalStatus.PROPOSED: {ProposalStatus.APPROVED, ProposalStatus.CORRECTED, ProposalStatus.REJECTED, ProposalStatus.NEEDS_REVIEW},
    ProposalStatus.NEEDS_REVIEW: {ProposalStatus.APPROVED, ProposalStatus.CORRECTED, ProposalStatus.REJECTED, ProposalStatus.UNMATCHED},
    ProposalStatus.UNMATCHED: {ProposalStatus.APPROVED, ProposalStatus.CORRECTED, ProposalStatus.REJECTED, ProposalStatus.NEEDS_REVIEW},
    ProposalStatus.APPROVED: {ProposalStatus.CORRECTED},
    ProposalStatus.CORRECTED: {ProposalStatus.APPROVED, ProposalStatus.CORRECTED},
    ProposalStatus.REJECTED: set(),
}


def validate_proposal_transition(current: str | ProposalStatus, target: str | ProposalStatus) -> None:
    current_status = ProposalStatus(current) if isinstance(current, str) else current
    target_status = ProposalStatus(target) if isinstance(target, str) else target

    if current_status == target_status:
        return

    allowed = VALID_PROPOSAL_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise InvalidStateTransitionError(
            f"Invalid proposal state transition from '{current_status.value}' to '{target_status.value}'."
        )


class EvaluationStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class FindingCategory(str, enum.Enum):
    CORRECT_UNDERSTANDING = "correct_understanding"
    PARTIALLY_CORRECT_UNDERSTANDING = "partially_correct_understanding"
    LIKELY_MISCONCEPTION = "likely_misconception"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class FindingReviewStatus(str, enum.Enum):
    PENDING_REVIEW = "pending_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"
    SUPERSEDED = "superseded"


class FindingReviewAction(str, enum.Enum):
    ACCEPT = "accepted"
    REJECT = "rejected"
    REQUEST_REVISION = "needs_revision"
    SUPERSEDE = "superseded"


VALID_FINDING_REVIEW_TRANSITIONS: dict[FindingReviewStatus, Set[FindingReviewStatus]] = {
    FindingReviewStatus.PENDING_REVIEW: {
        FindingReviewStatus.ACCEPTED,
        FindingReviewStatus.REJECTED,
        FindingReviewStatus.NEEDS_REVISION,
        FindingReviewStatus.SUPERSEDED,
    },
    FindingReviewStatus.NEEDS_REVISION: {
        FindingReviewStatus.ACCEPTED,
        FindingReviewStatus.REJECTED,
        FindingReviewStatus.NEEDS_REVISION,
        FindingReviewStatus.SUPERSEDED,
    },
    FindingReviewStatus.ACCEPTED: {
        FindingReviewStatus.NEEDS_REVISION,
        FindingReviewStatus.REJECTED,
        FindingReviewStatus.SUPERSEDED,
    },
    FindingReviewStatus.REJECTED: {
        FindingReviewStatus.NEEDS_REVISION,
        FindingReviewStatus.SUPERSEDED,
    },
    FindingReviewStatus.SUPERSEDED: set(),
}


def validate_finding_review_transition(
    current: str | FindingReviewStatus, target: str | FindingReviewStatus
) -> None:
    current_status = FindingReviewStatus(current) if isinstance(current, str) else current
    target_status = FindingReviewStatus(target) if isinstance(target, str) else target

    if current_status == target_status:
        return

    allowed = VALID_FINDING_REVIEW_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise InvalidStateTransitionError(
            f"Invalid finding review state transition from '{current_status.value}' to '{target_status.value}'."
        )


class RemediationRunStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    INSUFFICIENT_CONTEXT = "insufficient_context"


class PracticeQuestionType(str, enum.Enum):
    SHORT_ANSWER = "short_answer"
    MULTIPLE_CHOICE = "multiple_choice"
    EXPLAIN_REASONING = "explain_reasoning"


class PracticeItemReviewStatus(str, enum.Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


class PracticeItemReviewAction(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"


VALID_PRACTICE_ITEM_TRANSITIONS: dict[PracticeItemReviewStatus, Set[PracticeItemReviewStatus]] = {
    PracticeItemReviewStatus.PENDING_REVIEW: {
        PracticeItemReviewStatus.APPROVED,
        PracticeItemReviewStatus.REJECTED,
        PracticeItemReviewStatus.EDITED,
    },
    PracticeItemReviewStatus.EDITED: {
        PracticeItemReviewStatus.APPROVED,
        PracticeItemReviewStatus.REJECTED,
        PracticeItemReviewStatus.EDITED,
    },
    PracticeItemReviewStatus.APPROVED: {
        PracticeItemReviewStatus.EDITED,
        PracticeItemReviewStatus.REJECTED,
    },
    PracticeItemReviewStatus.REJECTED: {
        PracticeItemReviewStatus.EDITED,
    },
}


def validate_practice_item_transition(
    current: str | PracticeItemReviewStatus, target: str | PracticeItemReviewStatus
) -> None:
    current_status = PracticeItemReviewStatus(current) if isinstance(current, str) else current
    target_status = PracticeItemReviewStatus(target) if isinstance(target, str) else target

    if current_status == target_status:
        return

    allowed = VALID_PRACTICE_ITEM_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise InvalidStateTransitionError(
            f"Invalid practice item state transition from '{current_status.value}' to '{target_status.value}'."
        )


class PracticeSessionStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class FollowUpQuestionType(str, enum.Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    SHORT_ANSWER = "short_answer"
    NUMERICAL = "numerical"
    STEP_BASED = "step_based"


class FollowUpStatus(str, enum.Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class CorrectionFieldName(str, enum.Enum):
    MISCONCEPTION_HYPOTHESIS = "misconception_hypothesis"
    EVIDENCE_EXCERPT = "evidence_excerpt"
    LINKED_CONCEPT = "linked_concept"
    SEVERITY = "severity"
    CONFIDENCE_SCORE = "confidence_score"


class CorrectionStatus(str, enum.Enum):
    ACTIVE = "active"
    REVERTED = "reverted"


VALID_PRACTICE_SESSION_TRANSITIONS: dict[PracticeSessionStatus, Set[PracticeSessionStatus]] = {
    PracticeSessionStatus.ACTIVE: {
        PracticeSessionStatus.COMPLETED,
        PracticeSessionStatus.ABANDONED,
    },
    PracticeSessionStatus.COMPLETED: set(),
    PracticeSessionStatus.ABANDONED: set(),
}


def validate_practice_session_transition(
    current: str | PracticeSessionStatus, target: str | PracticeSessionStatus
) -> None:
    current_status = PracticeSessionStatus(current) if isinstance(current, str) else current
    target_status = PracticeSessionStatus(target) if isinstance(target, str) else target

    allowed = VALID_PRACTICE_SESSION_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise InvalidStateTransitionError(
            f"Invalid practice session state transition from '{current_status.value}' to '{target_status.value}'."
        )



