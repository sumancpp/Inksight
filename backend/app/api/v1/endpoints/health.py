from fastapi import APIRouter
from app.core.config import settings
from app.schemas.health import APIHealthResponse, AIHealthResponse

router = APIRouter()


@router.get(
    "/health/ai",
    response_model=AIHealthResponse,
    summary="AI Engine Health Check",
    description="Pings the configured AI Evaluator (vLLM / Groq) to verify live status.",
)
async def ai_health() -> AIHealthResponse:
    provider = settings.EVALUATOR_PROVIDER
    if provider == "mock":
        return AIHealthResponse(status="online", provider="mock", model="mock-evaluator")

    is_vllm = provider in ["vllm", "local_vllm", "openai"]
    if not is_vllm:
        return AIHealthResponse(
            status="offline",
            provider=provider,
            error=f"Unsupported evaluator provider: {provider}",
        )

    import httpx

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            headers = {"User-Agent": "Inksight/1.0"}
            if settings.VLLM_API_KEY:
                headers["Authorization"] = f"Bearer {settings.VLLM_API_KEY}"
            res = await client.get(f"{settings.VLLM_BASE_URL.rstrip('/')}/models", headers=headers)
            if res.status_code == 200:
                return AIHealthResponse(
                    status="online",
                    provider="vllm",
                    model=settings.VLLM_MODEL,
                )
            else:
                return AIHealthResponse(
                    status="offline",
                    provider="vllm",
                    model=settings.VLLM_MODEL,
                    error=f"HTTP {res.status_code}: {res.text[:120]}",
                )
    except Exception as exc:
        return AIHealthResponse(
            status="offline",
            provider="vllm",
            model=settings.VLLM_MODEL,
            error=f"{type(exc).__name__}: {str(exc)}",
        )


@router.get(
    "/health",
    response_model=APIHealthResponse,
    summary="API v1 Health Check",
    description="Returns current status, version, and environment for API v1.",
)
def api_v1_health() -> APIHealthResponse:
    return APIHealthResponse(
        status="ok",
        app_name=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        api_version="v1",
        ocr_provider=settings.OCR_PROVIDER,
        evaluator_provider=settings.EVALUATOR_PROVIDER,
        vllm_model=settings.VLLM_MODEL if settings.EVALUATOR_PROVIDER == "vllm" else None,
    )


@router.get(
    "/providers",
    summary="Get active OCR and AI Evaluator configuration status",
)
async def get_providers_status():
    is_vllm = settings.EVALUATOR_PROVIDER in ["vllm", "local_vllm", "openai"]
    vllm_reachable = False
    vllm_status_message = "VLLM is not configured as the active evaluator."

    if is_vllm:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                headers = {"User-Agent": "LearnGraph/1.0"}
                if settings.VLLM_API_KEY:
                    headers["Authorization"] = f"Bearer {settings.VLLM_API_KEY}"
                res = await client.get(f"{settings.VLLM_BASE_URL.rstrip('/')}/models", headers=headers)
                if res.status_code == 200:
                    vllm_reachable = True
                    vllm_status_message = f"VLLM endpoint online at {settings.VLLM_BASE_URL} (model: {settings.VLLM_MODEL})."
                else:
                    vllm_status_message = f"VLLM server returned HTTP {res.status_code} on probe."
        except Exception as exc:
            vllm_status_message = f"VLLM server unreachable at {settings.VLLM_BASE_URL} ({type(exc).__name__})."

    return {
        "ocr_provider": settings.OCR_PROVIDER,
        "ocr_real": settings.OCR_PROVIDER in ["paddleocr", "paddle"],
        "evaluator_provider": settings.EVALUATOR_PROVIDER,
        "evaluator_real": is_vllm,
        "vllm_base_url": settings.VLLM_BASE_URL,
        "vllm_model": settings.VLLM_MODEL,
        "vllm_timeout_seconds": settings.VLLM_TIMEOUT_SECONDS,
        "vllm_reachable": vllm_reachable,
        "vllm_status_message": vllm_status_message,
    }
