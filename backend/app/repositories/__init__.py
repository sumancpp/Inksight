"""Database repository access layer."""

from app.repositories.topic_repository import topic_repository
from app.repositories.assessment_repository import assessment_repository
from app.repositories.question_repository import question_repository
from app.repositories.submission_repository import submission_repository
from app.repositories.upload_repository import upload_repository
from app.repositories.ocr_repository import ocr_repository
from app.repositories.matching_repository import matching_repository
from app.repositories.evaluation_repository import EvaluationRepository, evaluation_repository
from app.repositories.remediation_repository import RemediationRepository, remediation_repository
from app.repositories.user_repository import UserRepository, user_repository

__all__ = [
    "user_repository",
    "UserRepository",
    "topic_repository",
    "assessment_repository",
    "question_repository",
    "submission_repository",
    "upload_repository",
    "ocr_repository",
    "matching_repository",
    "EvaluationRepository",
    "evaluation_repository",
    "RemediationRepository",
    "remediation_repository",
]




