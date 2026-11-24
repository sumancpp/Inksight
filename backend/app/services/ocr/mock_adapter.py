from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from app.services.ocr.base import BaseOCRAdapter, OCRAdapterError, OCRExtractionData
from app.services.ocr.layout import detect_math_content


class MockOCRAdapter(BaseOCRAdapter):
    """
    Deterministic mock OCR adapter for local development and testing.
    Does NOT perform real OCR or VLM processing.
    """

    def __init__(
        self,
        default_confidence: float = 0.92,
        force_empty: bool = False,
        force_low_confidence: bool = False,
        force_error: bool = False,
    ):
        self._default_confidence = default_confidence
        self.force_empty = force_empty
        self.force_low_confidence = force_low_confidence
        self.force_error = force_error

    @property
    def provider_name(self) -> str:
        return "mock_ocr_provider"

    async def extract(
        self,
        file_path: Path,
        on_progress: Optional[Callable[[int, int], Any]] = None,
    ) -> OCRExtractionData:
        if not file_path.exists():
            raise OCRAdapterError("File not found for extraction", error_code="FILE_NOT_FOUND")

        if on_progress:
            try:
                on_progress(1, 1)
            except Exception:
                pass

        # Read file bytes to check for deterministic test triggers
        try:
            content = file_path.read_bytes()
        except Exception as e:
            raise OCRAdapterError(f"Failed to read file: {e}", error_code="FILE_READ_ERROR")

        if self.force_error or b"MOCK_TRIGGER_ERROR" in content:
            raise OCRAdapterError("Simulated mock OCR extraction failure", error_code="ADAPTER_FAILURE")

        if self.force_empty or b"MOCK_TRIGGER_EMPTY" in content:
            return OCRExtractionData(
                extracted_text="",
                structured_segments=[],
                confidence=0.0,
                provider_name=self.provider_name,
                error_code="EMPTY_EXTRACTION",
            )

        if self.force_low_confidence or b"MOCK_TRIGGER_LOW_CONFIDENCE" in content:
            return OCRExtractionData(
                extracted_text="[Mock OCR - low confidence output] Difficult to decipher handwriting.",
                structured_segments=[
                    {
                        "segment_id": 1,
                        "page": 1,
                        "text": "Difficult to decipher handwriting.",
                        "confidence": 0.35,
                        "bounding_box": [10.0, 20.0, 100.0, 50.0],
                    }
                ],
                confidence=0.35,
                provider_name=self.provider_name,
                error_code=None,
            )

        # Standard deterministic successful mock result
        segments: List[Dict[str, Any]] = [
            {
                "segment_id": 1,
                "page": 1,
                "text": "Question 1: The derivative of f(x) = x^2 is f'(x) = 2x.",
                "confidence": 0.95,
                "bounding_box": [50.0, 100.0, 500.0, 150.0],
            },
            {
                "segment_id": 2,
                "page": 1,
                "text": "Question 2: According to Newton's second law, F = ma.",
                "confidence": 0.89,
                "bounding_box": [50.0, 200.0, 520.0, 250.0],
            },
        ]
        combined_text = "\n\n".join(seg["text"] for seg in segments)
        has_math, math_warnings = detect_math_content(combined_text)

        return OCRExtractionData(
            extracted_text=combined_text,
            structured_segments=segments,
            confidence=self._default_confidence,
            provider_name=self.provider_name,
            error_code=None,
            has_math_content=has_math,
            quality_warnings=math_warnings if has_math else None,
        )
