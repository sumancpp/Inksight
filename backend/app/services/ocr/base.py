from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class OCRAdapterError(Exception):
    """Raised when an OCR adapter encounters an execution error."""
    def __init__(self, message: str, error_code: str = "ADAPTER_EXECUTION_FAILED"):
        super().__init__(message)
        self.error_code = error_code


@dataclass
class OCRExtractionData:
    extracted_text: str
    structured_segments: List[Dict[str, Any]]
    confidence: Optional[float]
    provider_name: str
    error_code: Optional[str] = None
    has_math_content: Optional[bool] = None
    quality_warnings: Optional[List[str]] = None


class BaseOCRAdapter(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identification string."""
        pass

    @abstractmethod
    async def extract(
        self,
        file_path: Path,
        on_progress: Optional[Callable[[int, int], Any]] = None,
    ) -> OCRExtractionData:
        """
        Process the stored answer sheet file and return extracted text,
        structured segments, and confidence.
        Optional on_progress(pages_completed, total_pages) callback reports incremental progress.
        """
        pass
