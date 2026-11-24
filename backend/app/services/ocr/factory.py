from typing import Optional
from app.core.config import settings
from app.services.ocr.base import BaseOCRAdapter
from app.services.ocr.mock_adapter import MockOCRAdapter
from app.services.ocr.paddle_adapter import PaddleOCRAdapter


def get_ocr_adapter(provider_name: Optional[str] = None) -> BaseOCRAdapter:
    """
    Factory to retrieve the configured OCR adapter.
    Explicitly supports 'paddleocr' (real OCR) and 'mock' (test/demo).
    Never silently switches providers on failure.
    """
    provider = (provider_name or settings.OCR_PROVIDER).lower().strip()
    if provider == "mock":
        return MockOCRAdapter()
    if provider in ["paddleocr", "paddle"]:
        return PaddleOCRAdapter(
            lang=settings.PADDLEOCR_LANG,
            use_angle_cls=settings.PADDLEOCR_USE_ANGLE_CLS,
            use_gpu=settings.PADDLEOCR_USE_GPU,
            use_doc_unwarping=settings.PADDLEOCR_USE_DOC_UNWARPING,
            use_doc_orientation_classify=settings.PADDLEOCR_USE_DOC_ORIENTATION_CLASSIFY,
            render_scale=settings.PADDLEOCR_RENDER_SCALE,
            border_padding=settings.PADDLEOCR_BORDER_PADDING,
        )
    raise ValueError(
        f"Unsupported OCR provider: '{provider}'. "
        "Supported providers: ['paddleocr', 'mock']. Configure 'paddleocr' for real OCR."
    )
