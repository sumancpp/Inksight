import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
import httpx
import pytest

from app.models.enums import FindingCategory
from app.services.evaluator.base import EvaluationInput, EvaluatorError
from app.services.evaluator.factory import get_evaluator
from app.services.evaluator.vllm_evaluator import VLLMEvaluator


def test_vllm_factory_selection():
    """Verifies that the factory returns VLLMEvaluator when configured."""
    evaluator = get_evaluator("vllm")
    assert isinstance(evaluator, VLLMEvaluator)
    assert evaluator.provider_name == "vllm"

    evaluator_alias = get_evaluator("local_vllm")
    assert isinstance(evaluator_alias, VLLMEvaluator)


def test_no_silent_fallback_for_unknown_evaluator():
    """Verifies that an unsupported evaluator provider fails explicitly without silent fallback to mock."""
    with pytest.raises(ValueError) as exc_info:
        get_evaluator("unknown_evaluator_xyz")
    assert "Unsupported evaluator provider" in str(exc_info.value)
    assert "vllm" in str(exc_info.value)


def test_empty_student_answer_safety():
    """Verifies that empty student answers immediately produce INSUFFICIENT_EVIDENCE without network calls."""
    evaluator = VLLMEvaluator()
    payload = EvaluationInput(
        question_prompt="What is the derivative of x^2?",
        expected_answer="2x",
        student_answer="",
    )

    result = asyncio.run(evaluator.evaluate(payload))
    assert len(result.findings) == 1
    assert result.findings[0].category == FindingCategory.INSUFFICIENT_EVIDENCE
    assert "empty" in result.findings[0].rationale.lower()


def test_vllm_successful_evaluation():
    """Verifies end-to-end VLLM response parsing with valid findings and grounded evidence."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200

    student_answer_text = "I think the product rule is (f*g)' = f'*g' because you differentiate both."
    vllm_json_content = json.dumps(
        {
            "findings": [
                {
                    "concept_name": "Product Rule",
                    "category": "likely_misconception",
                    "confidence": 0.92,
                    "evidence_excerpt": "(f*g)' = f'*g'",
                    "rationale": "Student mistakenly equated product derivative to product of derivatives.",
                    "uncertainty_rationale": None,
                }
            ]
        }
    )
    mock_response.json.return_value = {
        "choices": [{"message": {"content": vllm_json_content}}]
    }
    mock_client.post.return_value = mock_response

    evaluator = VLLMEvaluator(
        base_url="http://localhost:8000/v1",
        model="Qwen2.5-7B",
        client=mock_client,
    )
    payload = EvaluationInput(
        question_prompt="State the product rule for derivatives.",
        expected_answer="f'g + fg'",
        student_answer=student_answer_text,
    )

    result = asyncio.run(evaluator.evaluate(payload))

    assert result.evaluator_name == "vllm:Qwen2.5-7B"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.concept_name == "Product Rule"
    assert finding.category == FindingCategory.LIKELY_MISCONCEPTION
    assert finding.confidence == 0.92
    assert finding.evidence_excerpt == "(f*g)' = f'*g'"


def test_vllm_evidence_grounding_rejection():
    """
    Verifies that ungrounded or hallucinated evidence excerpts not present in the student's answer
    are rejected, stripped, and flagged with an uncertainty rationale.
    """
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200

    student_answer_text = "The derivative of sin(x) is cos(x)."
    # Model hallucinated a quote not present in student answer
    vllm_json_content = json.dumps(
        {
            "findings": [
                {
                    "concept_name": "Chain Rule",
                    "category": "likely_misconception",
                    "confidence": 0.85,
                    "evidence_excerpt": "this text is completely hallucinated by the model",
                    "rationale": "Student showed misconception in non-existent text.",
                    "uncertainty_rationale": None,
                }
            ]
        }
    )
    mock_response.json.return_value = {
        "choices": [{"message": {"content": vllm_json_content}}]
    }
    mock_client.post.return_value = mock_response

    evaluator = VLLMEvaluator(client=mock_client)
    payload = EvaluationInput(
        question_prompt="What is the derivative of sin(x)?",
        student_answer=student_answer_text,
    )

    result = asyncio.run(evaluator.evaluate(payload))
    finding = result.findings[0]

    # Excerpt must be stripped because it was hallucinated
    assert finding.evidence_excerpt is None
    # Misconception must be downgraded to INSUFFICIENT_EVIDENCE
    assert finding.category == FindingCategory.INSUFFICIENT_EVIDENCE
    assert "Ungrounded evidence excerpt" in (finding.uncertainty_rationale or "")


def test_vllm_markdown_json_wrapping_handled():
    """Verifies that markdown code blocks (```json ... ```) are cleanly stripped and parsed."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200

    vllm_wrapped_content = "```json\n{\"findings\": [{\"concept_name\": \"Limits\", \"category\": \"correct_understanding\", \"confidence\": 0.95, \"evidence_excerpt\": \"limit is 0\", \"rationale\": \"Correct evaluation\", \"uncertainty_rationale\": null}]}\n```"
    mock_response.json.return_value = {
        "choices": [{"message": {"content": vllm_wrapped_content}}]
    }
    mock_client.post.return_value = mock_response

    evaluator = VLLMEvaluator(client=mock_client)
    payload = EvaluationInput(
        question_prompt="Find limit as x->inf of 1/x.",
        student_answer="The limit is 0 as x grows unbounded.",
    )

    result = asyncio.run(evaluator.evaluate(payload))
    assert len(result.findings) == 1
    assert result.findings[0].category == FindingCategory.CORRECT_UNDERSTANDING


def test_vllm_connection_failure():
    """Verifies that network connection failures raise EvaluatorError with VLLM_CONNECTION_FAILED."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ConnectError("Connection refused to 127.0.0.1:8000")

    evaluator = VLLMEvaluator(client=mock_client)
    payload = EvaluationInput(
        question_prompt="Prompt",
        student_answer="Student answer",
    )

    with pytest.raises(EvaluatorError) as exc_info:
        asyncio.run(evaluator.evaluate(payload))
    assert exc_info.value.error_code == "VLLM_CONNECTION_FAILED"
    assert "Cannot connect to local VLLM server" in str(exc_info.value)


def test_vllm_timeout():
    """Verifies that request timeouts raise EvaluatorError with VLLM_TIMEOUT."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.TimeoutException("Read timed out")

    evaluator = VLLMEvaluator(client=mock_client)
    payload = EvaluationInput(
        question_prompt="Prompt",
        student_answer="Student answer",
    )

    with pytest.raises(EvaluatorError) as exc_info:
        asyncio.run(evaluator.evaluate(payload))
    assert exc_info.value.error_code == "VLLM_TIMEOUT"


def test_vllm_api_error():
    """Verifies that HTTP error status codes raise EvaluatorError with VLLM_API_ERROR."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 502
    mock_response.text = "Bad Gateway: VLLM engine crashed"
    mock_client.post.return_value = mock_response

    evaluator = VLLMEvaluator(client=mock_client)
    payload = EvaluationInput(
        question_prompt="Prompt",
        student_answer="Student answer",
    )

    with pytest.raises(EvaluatorError) as exc_info:
        asyncio.run(evaluator.evaluate(payload))
    assert exc_info.value.error_code == "VLLM_API_ERROR"


def test_vllm_malformed_json():
    """Verifies that invalid/unparseable JSON returns safe degraded result with level='low' and requires_teacher_review=True."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "This is plain text, not JSON."}}]
    }
    mock_client.post.return_value = mock_response

    evaluator = VLLMEvaluator(client=mock_client)
    payload = EvaluationInput(
        question_prompt="Prompt",
        student_answer="Student answer",
    )

    result = asyncio.run(evaluator.evaluate(payload))
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.requires_teacher_review is True
    assert finding.confidence_details.level == "low"
    assert "evaluator_output_invalid" in finding.confidence_details.uncertainty_reasons
    assert finding.misconceptions == []


def test_vllm_invalid_schema():
    """Verifies that JSON with missing fields returns safe degraded result with level='low' and requires_teacher_review=True."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    # Missing required category and rationale
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "{\"findings\": [{\"concept_name\": \"Test\"}]}"}}]
    }
    mock_client.post.return_value = mock_response

    evaluator = VLLMEvaluator(client=mock_client)
    payload = EvaluationInput(
        question_prompt="Prompt",
        student_answer="Student answer",
    )

    result = asyncio.run(evaluator.evaluate(payload))
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.requires_teacher_review is True
    assert finding.confidence_details.level == "low"
    assert "evaluator_output_invalid" in finding.confidence_details.uncertainty_reasons
    assert finding.misconceptions == []

