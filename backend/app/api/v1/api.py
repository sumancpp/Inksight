from fastapi import APIRouter
from app.api.v1.endpoints import (
    analytics,
    assessments,
    auth,
    evaluations,
    health,
    matching,
    outcomes,
    practice,
    questions,
    remediation,
    submissions,
    topics,
    uploads,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication & RBAC"])
api_router.include_router(topics.router, prefix="/topics", tags=["Learning Topics"])
api_router.include_router(assessments.router, prefix="/assessments", tags=["Assessments"])
api_router.include_router(questions.router, prefix="/questions", tags=["Questions"])
api_router.include_router(submissions.router, prefix="/submissions", tags=["Submissions"])
api_router.include_router(uploads.router, tags=["Answer Sheets"])
api_router.include_router(matching.router, tags=["Answer Matching & Teacher Review"])
api_router.include_router(evaluations.router, tags=["AI Assessment & Misconception Evaluation"])
api_router.include_router(remediation.router, tags=["Targeted Remediation & Practice Generation"])
api_router.include_router(practice.router, tags=["Student Practice Sessions & Safe Delivery"])
api_router.include_router(outcomes.router, tags=["Intervention Outcomes & Follow-up Tracking"])
api_router.include_router(analytics.router, tags=["Class-Level Misconception Analytics"])



