import asyncio
import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from PIL import Image, ImageDraw

from app.services.ocr.base import OCRAdapterError
from app.services.ocr.factory import get_ocr_adapter
from app.services.ocr.paddle_adapter import PaddleOCRAdapter


def test_paddle_adapter_factory_selection():
    """Verifies that the factory returns PaddleOCRAdapter when configured."""
    adapter = get_ocr_adapter("paddleocr")
    assert isinstance(adapter, PaddleOCRAdapter)
    assert adapter.provider_name == "paddleocr"

    # Alternate alias
    adapter_alias = get_ocr_adapter("paddle")
    assert isinstance(adapter_alias, PaddleOCRAdapter)


def test_no_silent_fallback_for_unsupported_ocr_provider():
    """Verifies that an unsupported or misconfigured provider fails explicitly and does not silently fall back to mock."""
    with pytest.raises(ValueError) as exc_info:
        get_ocr_adapter("unknown_engine_xyz")
    assert "Unsupported OCR provider" in str(exc_info.value)
    assert "paddleocr" in str(exc_info.value)


def test_paddle_adapter_missing_file_raises_error(tmp_path: Path):
    """Verifies that attempting to extract a missing file raises OCRAdapterError with FILE_NOT_FOUND."""
    adapter = PaddleOCRAdapter(engine=MagicMock())
    missing_file = tmp_path / "does_not_exist.pdf"

    with pytest.raises(OCRAdapterError) as exc_info:
        asyncio.run(adapter.extract(missing_file))
    assert exc_info.value.error_code == "FILE_NOT_FOUND"


def test_paddle_adapter_extract_image_success(tmp_path: Path):
    """Verifies real OCR adapter parsing with a mocked PaddleOCR engine on an image file (v2 format)."""
    img_path = tmp_path / "test_answer.png"
    img = Image.new("RGB", (300, 100), color="white")
    img.save(img_path)

    mock_engine = MagicMock()
    mock_engine.ocr.return_value = [
        [
            [
                [[10.0, 20.0], [200.0, 20.0], [200.0, 50.0], [10.0, 50.0]],
                ("Question 1: The limit as x approaches 0 is 1", 0.945),
            ],
            [
                [[10.0, 60.0], [250.0, 60.0], [250.0, 90.0], [10.0, 90.0]],
                ("Question 2: Force equals mass times acceleration", 0.892),
            ],
        ]
    ]

    adapter = PaddleOCRAdapter(engine=mock_engine)
    result = asyncio.run(adapter.extract(img_path))

    assert result.provider_name == "paddleocr"
    assert result.error_code is None
    assert "Question 1: The limit" in result.extracted_text
    assert "Question 2: Force equals" in result.extracted_text
    assert len(result.structured_segments) == 2

    seg1 = result.structured_segments[0]
    assert seg1["segment_id"] == 1
    assert seg1["page"] == 1
    assert seg1["text"] == "Question 1: The limit as x approaches 0 is 1"
    assert seg1["confidence"] == 0.945
    assert seg1["bounding_box"] == [10.0, 20.0, 200.0, 50.0]

    expected_avg = round((0.945 + 0.892) / 2, 4)
    assert result.confidence == expected_avg


def test_paddle_adapter_extract_v3_dict_format(tmp_path: Path):
    """Verifies adapter parsing with PaddleOCR 3.x dict format (predict method)."""
    img_path = tmp_path / "v3_answer.png"
    Image.new("RGB", (300, 100), color="white").save(img_path)

    mock_engine = MagicMock()
    mock_engine.predict.return_value = [
        {
            "rec_texts": ["Photosynthesis produces oxygen", "Mitochondria is powerhouse"],
            "rec_scores": [0.962, 0.915],
            "rec_boxes": [[15.0, 25.0, 220.0, 55.0], [15.0, 65.0, 280.0, 95.0]],
        }
    ]

    adapter = PaddleOCRAdapter(engine=mock_engine)
    result = asyncio.run(adapter.extract(img_path))

    assert result.provider_name == "paddleocr"
    assert result.error_code is None
    assert "Photosynthesis produces oxygen" in result.extracted_text
    assert "Mitochondria is powerhouse" in result.extracted_text
    assert len(result.structured_segments) == 2

    seg1 = result.structured_segments[0]
    assert seg1["segment_id"] == 1
    assert seg1["page"] == 1
    assert seg1["text"] == "Photosynthesis produces oxygen"
    assert seg1["confidence"] == 0.962
    assert seg1["bounding_box"] == [15.0, 25.0, 220.0, 55.0]


def test_paddle_adapter_extract_pdf_success(tmp_path: Path):
    """Verifies that PDF pages are rendered and processed into structured segments."""
    pdf_bytes = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"
    )
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(pdf_bytes)

    mock_engine = MagicMock()
    mock_engine.predict.return_value = [
        {
            "rec_texts": ["f'(x) = 2x"],
            "rec_scores": [0.98],
            "rec_boxes": [[50.0, 50.0, 400.0, 80.0]],
        }
    ]

    adapter = PaddleOCRAdapter(engine=mock_engine, render_scale=2.0)
    result = asyncio.run(adapter.extract(pdf_path))

    assert result.provider_name == "paddleocr"
    assert result.extracted_text == "f'(x) = 2x"
    assert result.confidence == 0.98
    assert len(result.structured_segments) == 1
    assert result.structured_segments[0]["page"] == 1
    # Bounding box transformed from 2x pixel space back to PDF page points: 50.0 / 2.0 = 25.0
    assert result.structured_segments[0]["bounding_box"] == [25.0, 25.0, 200.0, 40.0]


def test_paddle_adapter_empty_page_handling(tmp_path: Path):
    """Verifies that a page with no detected text produces EMPTY_EXTRACTION cleanly."""
    img_path = tmp_path / "blank.png"
    Image.new("RGB", (100, 100), color="white").save(img_path)

    mock_engine = MagicMock()
    # PaddleOCR 3.x returns empty lists in dict for blank pages
    mock_engine.predict.return_value = [{"rec_texts": [], "rec_scores": [], "rec_boxes": []}]

    adapter = PaddleOCRAdapter(engine=mock_engine)
    result = asyncio.run(adapter.extract(img_path))

    assert result.extracted_text == ""
    assert result.structured_segments == []
    assert result.confidence is None
    assert result.error_code == "EMPTY_EXTRACTION"


def test_paddle_adapter_engine_exception_handling(tmp_path: Path):
    """Verifies that engine runtime crashes are wrapped as OCRAdapterError."""
    img_path = tmp_path / "corrupt.png"
    Image.new("RGB", (100, 100), color="white").save(img_path)

    mock_engine = MagicMock()
    mock_engine.predict.side_effect = RuntimeError("Paddle inference core failed")

    adapter = PaddleOCRAdapter(engine=mock_engine)
    with pytest.raises(OCRAdapterError) as exc_info:
        asyncio.run(adapter.extract(img_path))
    assert exc_info.value.error_code == "PADDLEOCR_EXECUTION_FAILED"


# =========================================================================
# REGRESSION AND INITIALIZATION TESTS (Task 5)
# =========================================================================

def test_paddle_adapter_init_failure_regression():
    """
    Regression test: Verifies that when PaddleOCR.__init__ raises an error
    (such as ValueError: Unknown argument: use_gpu), an OCRAdapterError with
    error_code='PADDLEOCR_INIT_FAILED' is raised, and the error message does
    NOT leak local file paths or internal secrets.
    """
    with patch("paddleocr.PaddleOCR", side_effect=ValueError("Unknown argument: use_gpu")):
        adapter = PaddleOCRAdapter(engine=None)
        with pytest.raises(OCRAdapterError) as exc_info:
            adapter._get_engine()

        assert exc_info.value.error_code == "PADDLEOCR_INIT_FAILED"
        err_msg = str(exc_info.value)
        assert "PaddleOCR initialization failed" in err_msg
        # Safe actionable message: must not leak filesystem paths or secrets
        assert "/home/" not in err_msg
        assert "/root/" not in err_msg
        assert "use_gpu" not in err_msg  # internal stack detail hidden from API response


def test_paddle_adapter_successful_init_v3_signature():
    """
    Verifies that _build_init_kwargs adapts cleanly to PaddleOCR 3.x constructor
    signature (use_textline_orientation, device='cpu', enable_mkldnn=False,
    use_doc_unwarping=False, use_doc_orientation_classify=False).
    """
    class MockPaddleOCRv3:
        def __init__(
            self,
            lang=None,
            use_textline_orientation=None,
            use_doc_unwarping=None,
            use_doc_orientation_classify=None,
            **kwargs,
        ):
            self.lang = lang
            self.use_textline_orientation = use_textline_orientation
            self.use_doc_unwarping = use_doc_unwarping
            self.use_doc_orientation_classify = use_doc_orientation_classify
            self.kwargs = kwargs

    adapter = PaddleOCRAdapter(
        engine=None,
        lang="en",
        use_angle_cls=True,
        use_gpu=False,
    )
    init_kwargs = adapter._build_init_kwargs(MockPaddleOCRv3)

    assert init_kwargs["lang"] == "en"
    assert init_kwargs["use_textline_orientation"] is True
    assert init_kwargs["device"] == "cpu"
    assert init_kwargs["enable_mkldnn"] is False
    assert init_kwargs["use_doc_unwarping"] is False
    assert init_kwargs["use_doc_orientation_classify"] is False
    assert "use_gpu" not in init_kwargs  # must not pass use_gpu to v3


def test_paddle_adapter_successful_init_v2_signature():
    """
    Verifies backward compatibility with PaddleOCR 2.x constructor signature
    (use_gpu=False, use_angle_cls=True).
    """
    class MockPaddleOCRv2:
        def __init__(
            self,
            use_angle_cls=True,
            lang="ch",
            use_gpu=False,
            **kwargs,
        ):
            self.use_angle_cls = use_angle_cls
            self.lang = lang
            self.use_gpu = use_gpu

    adapter = PaddleOCRAdapter(
        engine=None,
        lang="en",
        use_angle_cls=True,
        use_gpu=False,
    )
    init_kwargs = adapter._build_init_kwargs(MockPaddleOCRv2)

    assert init_kwargs["lang"] == "en"
    assert init_kwargs["use_angle_cls"] is True
    assert init_kwargs["use_gpu"] is False
    assert "device" not in init_kwargs


def test_bbox_coordinate_transformation_with_scale_and_padding():
    """
    Verifies that _calculate_bbox correctly shifts padding and scales coordinates
    back to the original page coordinate space.
    """
    adapter = PaddleOCRAdapter()

    # Raw box in 2.0x scale with 10px padding: [50, 50, 210, 90]
    # Transformed: (50 - 10) / 2.0 = 20.0; (210 - 10) / 2.0 = 100.0; (90 - 10) / 2.0 = 40.0
    bbox_4 = adapter._calculate_bbox([50.0, 50.0, 210.0, 90.0], scale=2.0, pad_x=10, pad_y=10)
    assert bbox_4 == [20.0, 20.0, 100.0, 40.0]

    # Polygon format
    poly = [[50.0, 50.0], [210.0, 50.0], [210.0, 90.0], [50.0, 90.0]]
    bbox_poly = adapter._calculate_bbox(poly, scale=2.0, pad_x=10, pad_y=10)
    assert bbox_poly == [20.0, 20.0, 100.0, 40.0]

    # Zero padding and 1.0 scale (image passthrough)
    passthrough = adapter._calculate_bbox([15.0, 25.0, 100.0, 50.0], scale=1.0, pad_x=0, pad_y=0)
    assert passthrough == [15.0, 25.0, 100.0, 50.0]


def test_live_pdf_ocr_extraction(tmp_path: Path):
    """
    Live OCR test on an actual PDF document rendered with real PaddleOCR.
    Verifies actual text extraction, confidence scoring, and segment structure.
    """
    # 1. Create a real PDF containing clear text
    pdf_path = tmp_path / "actual_test.pdf"
    img = Image.new("RGB", (600, 160), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 60), "Student Answer: DNA contains genetic instructions.", fill="black")
    img.save(str(pdf_path), "PDF")

    # 2. Run live PaddleOCRAdapter
    adapter = PaddleOCRAdapter()
    result = asyncio.run(adapter.extract(pdf_path))

    # 3. Assert extraction properties
    assert result.provider_name == "paddleocr"
    assert result.error_code is None
    assert len(result.structured_segments) >= 1
    first_seg = result.structured_segments[0]
    assert first_seg["page"] == 1
    assert "DNA" in first_seg["text"] or "genetic" in first_seg["text"] or "instructions" in first_seg["text"]
    assert first_seg["confidence"] is not None
    assert first_seg["confidence"] > 0.5
    assert first_seg["bounding_box"] is not None
    assert len(first_seg["bounding_box"]) == 4


def test_edge_lines_pdf_regression(tmp_path: Path):
    """
    REGRESSION TEST (Edge Lines Missing Fix):
    Verifies that a multi-line PDF with text located on the first line near the
    top edge (y=10), in the middle (y=400), and on the last line near the bottom
    edge (y=770) are ALL detected and extracted by real PaddleOCR.

    Confirms that:
    1. The top header line is not lost/cropped by document preprocessor/unwarping.
    2. The bottom footer line is not lost/cropped by document preprocessor/unwarping.
    3. Segments are returned in top-to-bottom reading order.
    4. Bounding boxes are scaled back to the 600x800 page coordinate system.
    """
    # 1. Generate a 600x800 PDF with edge lines
    pdf_path = tmp_path / "edge_lines_test.pdf"
    img = Image.new("RGB", (600, 800), color="white")
    draw = ImageDraw.Draw(img)
    # First line near top edge (y=10)
    draw.text((20, 10), "TOP HEADER: Student Name: Alex Doe | Subject: Physics", fill="black")
    # Middle line (y=400)
    draw.text((20, 400), "MIDDLE CONTENT: Newton Third Law states equal and opposite reaction.", fill="black")
    # Last line near bottom edge (y=770)
    draw.text((20, 770), "BOTTOM FOOTER: Page 1 of 1 -- Examination Board 2026", fill="black")
    img.save(str(pdf_path), "PDF")

    # 2. Run real PaddleOCRAdapter (unwarping=False, scale=2.0)
    adapter = PaddleOCRAdapter()
    result = asyncio.run(adapter.extract(pdf_path))

    # 3. Assertions
    assert result.provider_name == "paddleocr"
    assert result.error_code is None
    extracted = result.extracted_text

    # Verify all 3 lines are present in the final output text
    assert "TOP HEADER" in extracted or "Alex Doe" in extracted, f"Top line missing from OCR text: {repr(extracted)}"
    assert "MIDDLE CONTENT" in extracted or "Newton" in extracted, f"Middle line missing from OCR text: {repr(extracted)}"
    assert "BOTTOM FOOTER" in extracted or "Examination Board" in extracted, f"Bottom line missing from OCR text: {repr(extracted)}"

    # Verify structured segments count and order
    assert len(result.structured_segments) >= 3, f"Expected at least 3 segments, got {len(result.structured_segments)}"
    top_seg = result.structured_segments[0]
    bottom_seg = result.structured_segments[-1]

    # Verify top line is at the top of the page coordinate system (y_min < 50.0)
    assert top_seg["bounding_box"] is not None
    assert top_seg["bounding_box"][1] < 50.0, f"Top line y_min should be < 50, got {top_seg['bounding_box']}"

    # Verify bottom line is near the bottom of the page coordinate system (y_max > 700.0)
    assert bottom_seg["bounding_box"] is not None
    assert bottom_seg["bounding_box"][3] > 700.0, f"Bottom line y_max should be > 700, got {bottom_seg['bounding_box']}"

    # Verify all coordinates are bounded within the 600x800 page coordinate system
    for seg in result.structured_segments:
        bbox = seg["bounding_box"]
        assert bbox[0] >= 0.0 and bbox[1] >= 0.0
        assert bbox[2] <= 600.0 + 10.0  # within page width
        assert bbox[3] <= 800.0 + 10.0  # within page height


def test_math_and_multicolumn_layout_ordering_regression():
    """
    REGRESSION TEST (Math & Multi-column Layout Ordering):
    Verifies that:
    1. A multi-column document does NOT interleave lines horizontally across columns.
    2. Spanning headers come first, left column comes next, right column follows,
       middle spanning divider separates sections, and bottom footer comes last.
    3. Mathematical symbols (integrals, superscripts, subscripts, matrices) are detected,
       setting has_math_content=True and generating advisory quality warnings.
    4. Original OCR text and bounding boxes are preserved without fabrication.
    """
    from app.services.ocr.layout import detect_math_content, order_page_segments

    # Page dimension: 1000 x 1400
    # Header: y = 20..60, spanning x = 50..950
    # Left col: x = 50..450, y = 100..250
    # Right col: x = 550..950, y = 100..250 (vertically overlapping left col)
    # Middle banner: y = 350..390, spanning x = 50..950
    # Bottom left col: x = 50..450, y = 420..500
    # Bottom right col: x = 550..950, y = 420..500
    # Bottom footer: y = 1300..1340, spanning x = 50..950

    segments = [
        # Right col row 1 (y=100)
        {"text": "Right Col 1: Part B Linear Algebra", "bounding_box": [550.0, 100.0, 950.0, 130.0], "confidence": 0.95},
        # Left col row 1 (y=105)
        {"text": "Left Col 1: Part A Calculus int x^2 dx", "bounding_box": [50.0, 105.0, 450.0, 135.0], "confidence": 0.94},
        # Spanning Top Header (y=20)
        {"text": "TOP HEADER: Higher Engineering Mathematics", "bounding_box": [50.0, 20.0, 950.0, 60.0], "confidence": 0.98},
        # Right col row 2 (y=180) - matrix notation
        {"text": "Right Col 2: Matrix [a b ; c d] det=ad-bc", "bounding_box": [550.0, 180.0, 950.0, 210.0], "confidence": 0.91},
        # Left col row 2 (y=185) - derivative
        {"text": "Left Col 2: Derivative d/dx(e^x) = e^x", "bounding_box": [50.0, 185.0, 450.0, 215.0], "confidence": 0.92},
        # Middle spanning section (y=350)
        {"text": "MIDDLE BANNER: Section II Geometry", "bounding_box": [50.0, 350.0, 950.0, 390.0], "confidence": 0.97},
        # Bottom footer (y=1300)
        {"text": "BOTTOM FOOTER: Page 1 of 1 Exam Board", "bounding_box": [50.0, 1300.0, 950.0, 1340.0], "confidence": 0.99},
    ]

    ordered = order_page_segments(segments)
    ordered_texts = [s["text"] for s in ordered]

    # Verify order: Header -> Left Col 1 -> Left Col 2 -> Right Col 1 -> Right Col 2 -> Middle Banner -> Bottom Footer
    assert ordered_texts[0].startswith("TOP HEADER"), f"Expected header first, got: {ordered_texts[0]}"
    assert ordered_texts[1].startswith("Left Col 1"), f"Expected Left Col 1, got: {ordered_texts[1]}"
    assert ordered_texts[2].startswith("Left Col 2"), f"Expected Left Col 2, got: {ordered_texts[2]}"
    assert ordered_texts[3].startswith("Right Col 1"), f"Expected Right Col 1, got: {ordered_texts[3]}"
    assert ordered_texts[4].startswith("Right Col 2"), f"Expected Right Col 2, got: {ordered_texts[4]}"
    assert ordered_texts[5].startswith("MIDDLE BANNER"), f"Expected Middle Banner, got: {ordered_texts[5]}"
    assert ordered_texts[6].startswith("BOTTOM FOOTER"), f"Expected Bottom Footer, got: {ordered_texts[6]}"

    # Verify math content detection
    has_math, warnings = detect_math_content(ordered)
    assert has_math is True
    assert len(warnings) > 0
    assert any("mathematical" in w.lower() or "formula" in w.lower() for w in warnings)


def test_paddle_adapter_streaming_progress_callback(tmp_path: Path):
    """
    Verifies that PaddleOCRAdapter invokes on_progress(page_num, total_pages)
    incrementally during multi-page PDF processing.
    """
    # Create a 2-page PDF
    pdf_path = tmp_path / "two_pages.pdf"
    img1 = Image.new("RGB", (200, 200), color="white")
    draw1 = ImageDraw.Draw(img1)
    draw1.text((10, 10), "Page 1 Content", fill="black")

    img2 = Image.new("RGB", (200, 200), color="white")
    draw2 = ImageDraw.Draw(img2)
    draw2.text((10, 10), "Page 2 Content", fill="black")

    img1.save(str(pdf_path), "PDF", save_all=True, append_images=[img2])

    mock_engine = MagicMock()
    mock_engine.ocr.return_value = [
        [
            [[[10.0, 10.0], [100.0, 10.0], [100.0, 30.0], [10.0, 30.0]], ("Page Text", 0.95)]
        ]
    ]

    adapter = PaddleOCRAdapter(engine=mock_engine)

    progress_reports = []
    def progress_cb(current, total):
        progress_reports.append((current, total))

    result = asyncio.run(adapter.extract(pdf_path, on_progress=progress_cb))

    assert result.error_code is None
    # Progress callback reports (0, total) initially, then (1, total), (2, total)
    assert progress_reports == [(0, 2), (1, 2), (2, 2)], f"Expected incremental progress, got: {progress_reports}"


