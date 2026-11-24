import json
import re
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.core.logging import logger
from app.models.enums import FindingCategory, FollowUpQuestionType
from app.schemas.evaluation import ConfidenceDetails, FindingOutput, MisconceptionItem, derive_requires_teacher_review
from app.schemas.follow_up import FollowUpQuestionPayload, FollowUpRubric, RubricCriterion
from app.services.evaluator.base import (
    BaseEvaluator,
    EvaluationInput,
    EvaluationResult,
    EvaluatorError,
    FollowUpGenerationInput,
)


class VLLMFindingsPayload(BaseModel):
    findings: List[FindingOutput] = Field(default_factory=list)


FOLLOWUP_SYSTEM_PROMPT = """You are an expert diagnostic educational evaluator.
Your role is to generate ONE targeted diagnostic follow-up question that directly checks whether a student's suspected misconception is present or resolved.

Rules:
1. The follow-up question MUST directly test the specific linked concept and suspected misconception.
2. The question_text MUST explicitly mention or incorporate the linked concept name (e.g. "In <concept>, ...", "Regarding <concept>, ...") to ensure the question is conceptually grounded.
3. Provide a deterministic expected answer.
4. Provide a clear rubric with criteria and positive marks. Total marks must be > 0.
5. Return ONLY a valid JSON object matching this exact schema:
{
  "concept": "<Exact linked concept string>",
  "question_text": "<Clear question explicitly naming or containing the concept>",
  "expected_answer": "<Precise expected model answer>",
  "rubric": {
    "criteria": [
      {"text": "<Criterion description>", "marks": 1.0}
    ]
  },
  "question_type": "short_answer" | "multiple_choice" | "numerical" | "step_based"
}
"""


SYSTEM_PROMPT = """You are an expert diagnostic educational evaluator.
Your role is to assess a student's answer against a question prompt, rubric criteria, expected answer, topic context, and marks available.

Analyze the answer for conceptual understanding, procedural correctness, misconceptions, and evidence.
Adhere strictly to these evaluation rules:
1. Category must be one of:
   - "correct_understanding": Student exhibits complete conceptual understanding.
   - "partially_correct_understanding": Student demonstrates partial understanding but has minor procedural, step, or reasoning gaps.
   - "likely_misconception": Student demonstrates a specific conceptual flaw or mistaken rule/model.
   - "insufficient_evidence": The student answer is missing, unrelated, or lacks enough information to evaluate understanding.
2. Verdict must be one of:
   - "correct": Completely correct answer and steps.
   - "partially_correct": Partial understanding or steps demonstrated.
   - "incorrect": Incorrect answer or major misconception.
   - "needs_teacher_review": Ambiguous, ungrounded, or missing rubric/answer key.
3. Diagnostic Details:
   - "correct_answer": The expected correct answer or model solution.
   - "marks_awarded": Numeric marks awarded (bounded between 0.0 and max_marks available).
   - "max_marks": Total marks available for the question.
   - "marks_reason": Short justification for the marks awarded.
   - "error_amount": If applicable (e.g. arithmetic difference like "+1" or "-3"), state it; otherwise null.
   - "error_type": Classification of error (e.g. "arithmetic_calculation_error", "missing_step", "conceptual_rule_confusion", or null).
   - "step_by_step_explanation": Clear pedagogical breakdown explaining what is right, where the work first goes wrong, and how to fix it.
   - "misconceptions": A structured array of hypothesized misconceptions (omit or leave empty if none):
     [
       {
         "hypothesis": "Hypothesized conceptual misunderstanding or flawed rule (never present as certainty)",
         "evidence_excerpt": "Direct exact verbatim substring quoted from student's answer",
         "linked_concept": "Specific concept or rule name",
         "severity": "low" | "medium" | "high"
       }
     ]
     IMPORTANT: Only include a misconception if evidence_excerpt is an exact quote from the student's answer. If no evidence, omit.
   - "remediation_concept": The exact topic or skill the student should review.
   - "follow_up_question": Exactly one targeted follow-up question to test whether the gap is resolved.
4. Evidence Grounding:
   - "evidence_excerpt" MUST be an exact, verbatim substring quoted directly from the student's answer.
   - Do NOT paraphrase, invent, or extrapolate evidence excerpts. If there is no specific quote, set evidence_excerpt to null.
5. Rationales & Confidence:
   - "rationale" must clearly explain what the student understood or misunderstood.
   - "confidence_details":
     {
       "score": 0.85, # float between 0.0 and 1.0 representing diagnostic certainty
       "level": "low" | "medium" | "high", # score < 0.70 or ambiguous rubric or insufficient evidence MUST be "low"
       "uncertainty_reasons": ["Short reason for uncertainty if level is low, else empty"]
     }
   - "uncertainty_rationale" should explain any ambiguity, missing context, or handwriting/OCR doubt.
6. Output Format:
   - You MUST output a single valid JSON object strictly matching this schema:
     {
       "findings": [
         {
           "concept_name": "Name of concept (e.g. Chain Rule, Newton's 2nd Law, Arithmetic Addition)",
           "category": "correct_understanding" | "partially_correct_understanding" | "likely_misconception" | "insufficient_evidence",
           "confidence": 0.85,
           "evidence_excerpt": "exact quote from student answer or null",
           "rationale": "Detailed pedagogical explanation",
           "uncertainty_rationale": "Any reason for diagnostic uncertainty or null",
           "verdict": "correct" | "partially_correct" | "incorrect" | "needs_teacher_review",
           "correct_answer": "Model solution or expected value",
           "marks_awarded": 0.0,
           "max_marks": 1.0,
           "marks_reason": "Justification of score",
           "error_amount": "+1 or null",
           "error_type": "arithmetic_calculation_error or missing_step or null",
           "step_by_step_explanation": "Pedagogical step breakdown",
           "misconceptions": [
             {
               "hypothesis": "Hypothesized conceptual flaw",
               "evidence_excerpt": "exact quote from student answer",
               "linked_concept": "Concept name",
               "severity": "medium"
             }
           ],
           "confidence_details": {
             "score": 0.85,
             "level": "high",
             "uncertainty_reasons": []
           },
           "remediation_concept": "Concept to review",
           "follow_up_question": "One targeted follow-up question"
         }
       ]
     }
"""


class VLLMEvaluator(BaseEvaluator):
    """
    OpenAI-compatible HTTP adapter for local VLLM servers serving diagnostic evaluation.
    Communicates via /v1/chat/completions with strict JSON schema validation and evidence-grounding checks.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        raw_url = base_url or settings.VLLM_BASE_URL
        self.base_url = raw_url.rstrip("/")
        self.model = model or settings.VLLM_MODEL
        self.timeout = timeout if timeout is not None else settings.VLLM_TIMEOUT_SECONDS
        self.api_key = api_key if api_key is not None else settings.VLLM_API_KEY
        self.temperature = temperature if temperature is not None else settings.VLLM_TEMPERATURE
        self._external_client = client

    @property
    def provider_name(self) -> str:
        return "vllm"

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "LearnGraph/1.0",
        }
        if self.api_key and self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"
        return headers

    def _build_user_message(self, payload: EvaluationInput) -> str:
        parts = [
            f"Question Prompt:\n{payload.question_prompt.strip()}",
            f"Marks Available: {payload.marks if payload.marks is not None else 1.0}",
        ]
        if payload.question_type:
            parts.append(f"Question Type: {payload.question_type}")
        if payload.topic_name:
            parts.append(f"Topic Context:\n{payload.topic_name.strip()}")
        if payload.expected_answer:
            parts.append(f"Expected Answer / Solution Criteria:\n{payload.expected_answer.strip()}")
        if payload.rubric:
            parts.append(f"Evaluation Rubric:\n{payload.rubric.strip()}")

        parts.append(f"Student Submitted Answer (Evaluate This):\n{payload.student_answer.strip()}")
        return "\n\n".join(parts)

    def _build_degraded_result(self, payload: EvaluationInput, reason: str) -> EvaluationResult:
        logger.warning(f"VLLMEvaluator: Returning safe degraded result due to: {reason}")
        return EvaluationResult(
            evaluator_name=f"{self.provider_name}:{self.model}",
            findings=[
                FindingOutput(
                    concept_name=payload.topic_name or "Assessment Concept",
                    category=FindingCategory.INSUFFICIENT_EVIDENCE,
                    confidence=0.40,
                    confidence_details=ConfidenceDetails(
                        score=0.40,
                        level="low",
                        uncertainty_reasons=["evaluator_output_invalid", reason],
                    ),
                    requires_teacher_review=True,
                    misconceptions=[],
                    uncertainty_rationale=f"Evaluator output was invalid or unparseable: {reason}. Teacher review required.",
                    evidence_excerpt=None,
                    rationale=f"Diagnostic evaluation degraded safely because model response was invalid ({reason}).",
                    verdict="needs_teacher_review",
                    correct_answer=payload.expected_answer,
                    marks_awarded=0.0,
                    max_marks=float(payload.marks if payload.marks is not None else 1.0),
                    marks_reason="Degraded evaluation awaiting teacher review.",
                )
            ],
        )

    def _validate_evidence_grounding(
        self, findings: List[FindingOutput], student_answer: str
    ) -> List[FindingOutput]:
        """
        Validates that any evidence_excerpt provided is an exact substring of the student's answer.
        Ungrounded quotes are rejected and flagged to prevent model hallucinations.
        """
        norm_student = " ".join((student_answer or "").lower().split())
        grounded_findings: List[FindingOutput] = []

        for finding in findings:
            excerpt = (finding.evidence_excerpt or "").strip()
            if excerpt:
                norm_excerpt = " ".join(excerpt.lower().split())
                if norm_excerpt not in norm_student:
                    logger.warning(
                        f"VLLM Evaluator: Rejecting ungrounded evidence excerpt '{excerpt}' "
                        f"not present in student answer."
                    )
                    ungrounded_note = (
                        f"[Ungrounded evidence excerpt '{excerpt}' rejected: quote not found in student answer.]"
                    )
                    finding.uncertainty_rationale = (
                        f"{ungrounded_note} {finding.uncertainty_rationale or ''}"
                    ).strip()
                    finding.evidence_excerpt = None
                    if finding.category == FindingCategory.LIKELY_MISCONCEPTION:
                        finding.category = FindingCategory.INSUFFICIENT_EVIDENCE
                        finding.rationale = (
                            f"{finding.rationale} (Note: Cited evidence could not be verified in student text.)"
                        )

            # Grounding validation for structured misconceptions
            grounded_misconceptions: List[MisconceptionItem] = []
            attempted_misconceptions = len(finding.misconceptions or [])
            for item in (finding.misconceptions or []):
                norm_item_excerpt = " ".join((item.evidence_excerpt or "").lower().split())
                if norm_item_excerpt and norm_item_excerpt in norm_student:
                    grounded_misconceptions.append(item)
                else:
                    logger.warning(
                        f"VLLM Evaluator: Dropping ungrounded misconception excerpt '{item.evidence_excerpt}'."
                    )

            finding.misconceptions = grounded_misconceptions

            if not finding.confidence_details:
                score = float(finding.confidence if finding.confidence is not None else 0.5)
                level = "low" if score < 0.70 else ("medium" if score < 0.85 else "high")
                finding.confidence_details = ConfidenceDetails(score=score, level=level, uncertainty_reasons=[])

            # If all attempted misconceptions were ungrounded and dropped, set level = "low"
            if attempted_misconceptions > 0 and len(grounded_misconceptions) == 0:
                finding.confidence_details.level = "low"
                if "no_grounded_misconception_evidence" not in finding.confidence_details.uncertainty_reasons:
                    finding.confidence_details.uncertainty_reasons.append("no_grounded_misconception_evidence")

            finding.requires_teacher_review = derive_requires_teacher_review(finding.confidence_details)
            finding.confidence = finding.confidence_details.score
            if finding.misconceptions and len(finding.misconceptions) > 0:
                finding.misconception_hypothesis = finding.misconceptions[0].hypothesis

            grounded_findings.append(finding)

        return grounded_findings

    async def evaluate(self, payload: EvaluationInput) -> EvaluationResult:
        student_text = (payload.student_answer or "").strip()

        # Safety Guard: Empty student answer cannot be evaluated for conceptual misconceptions
        if not student_text:
            return EvaluationResult(
                evaluator_name=f"{self.provider_name}:{self.model}",
                findings=[
                    FindingOutput(
                        concept_name=payload.topic_name or "Assessment Concept",
                        category=FindingCategory.INSUFFICIENT_EVIDENCE,
                        confidence=1.0,
                        uncertainty_rationale="Student submitted answer is empty.",
                        evidence_excerpt=None,
                        rationale="Student answer is empty; cannot evaluate conceptual understanding without submitted text.",
                    )
                ],
            )

        endpoint = f"{self.base_url}/chat/completions"
        request_body: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self._build_user_message(payload)},
            ],
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }

        # Mask API key in debug logs
        logger.info(
            f"VLLMEvaluator: Sending request to {endpoint} (model='{self.model}', timeout={self.timeout}s)"
        )

        try:
            if self._external_client:
                response = await self._external_client.post(
                    endpoint,
                    json=request_body,
                    headers=self._get_headers(),
                    timeout=self.timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        endpoint,
                        json=request_body,
                        headers=self._get_headers(),
                    )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            logger.error(f"VLLMEvaluator: Connection failed to {endpoint}: {exc}")
            raise EvaluatorError(
                f"Cannot connect to local VLLM server at {self.base_url}. "
                f"Ensure the VLLM instance is running (e.g. 'vllm serve {self.model}').",
                error_code="VLLM_CONNECTION_FAILED",
            )
        except httpx.TimeoutException as exc:
            logger.error(f"VLLMEvaluator: Request timed out after {self.timeout}s: {exc}")
            raise EvaluatorError(
                f"VLLM evaluation timed out after {self.timeout}s.",
                error_code="VLLM_TIMEOUT",
            )
        except Exception as exc:
            logger.error(f"VLLMEvaluator: Unexpected transport error: {exc}")
            raise EvaluatorError(
                f"VLLM communication error: {exc}",
                error_code="VLLM_TRANSPORT_ERROR",
            )

        if response.status_code != 200:
            logger.error(f"VLLMEvaluator: API returned status {response.status_code}: {response.text}")
            raise EvaluatorError(
                f"VLLM server returned HTTP {response.status_code}: {response.text[:200]}",
                error_code="VLLM_API_ERROR",
            )

        # Parse JSON from response
        try:
            resp_json = response.json()
        except Exception as exc:
            logger.error(f"VLLMEvaluator: Failed to parse VLLM response as JSON: {exc}")
            return self._build_degraded_result(payload, "evaluator_output_invalid: response not JSON")

        # Extract content from chat completion choice
        try:
            choices = resp_json.get("choices", [])
            if not choices:
                raise KeyError("No 'choices' returned in completion response")
            content_str = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            logger.error(f"VLLMEvaluator: Invalid chat completion structure from VLLM: {exc}")
            return self._build_degraded_result(payload, "evaluator_output_invalid: missing choices")

        # Clean JSON markdown if wrapped in ```json ... ```
        clean_content = content_str.strip()
        if clean_content.startswith("```"):
            clean_content = re.sub(r"^```(?:json)?\s*", "", clean_content)
            clean_content = re.sub(r"\s*```$", "", clean_content)

        try:
            parsed_data = json.loads(clean_content)
        except json.JSONDecodeError as exc:
            logger.error(f"VLLMEvaluator: Output choice content is not valid JSON: {exc}")
            return self._build_degraded_result(payload, "evaluator_output_invalid: invalid JSON in completion")

        # Validate with Pydantic
        try:
            validated_payload = VLLMFindingsPayload.model_validate(parsed_data)
        except ValidationError as exc:
            logger.error(f"VLLMEvaluator: Pydantic schema validation error: {exc}")
            return self._build_degraded_result(payload, "evaluator_output_invalid: schema validation failed")

        # Validate evidence grounding against student answer
        grounded_findings = self._validate_evidence_grounding(
            findings=validated_payload.findings,
            student_answer=student_text,
        )

        return EvaluationResult(
            evaluator_name=f"{self.provider_name}:{self.model}",
            findings=grounded_findings,
        )

    async def generate_follow_up(self, payload: FollowUpGenerationInput) -> FollowUpQuestionPayload:
        user_prompt = (
            f"Original Question: {payload.question_prompt}\n"
            f"Student Answer: {payload.student_answer}\n"
            f"Suspected Misconception Hypothesis: {payload.misconception_hypothesis}\n"
            f"Linked Concept: {payload.linked_concept}\n"
            f"Evidence Excerpt: {payload.evidence_excerpt or 'N/A'}\n\n"
            "Generate ONE diagnostic follow-up question testing this misconception with expected answer and rubric."
        )
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": FOLLOWUP_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=request_body, headers=headers)
                resp.raise_for_status()
                response_json = resp.json()
        except Exception as exc:
            logger.error(f"VLLMEvaluator: Follow-up generation HTTP call failed: {exc}")
            raise EvaluatorError(f"Follow-up generation network error: {exc}")

        try:
            choices = response_json.get("choices")
            if not choices:
                raise KeyError("No 'choices' returned in completion response")
            content_str = choices[0]["message"]["content"]
        except Exception as exc:
            logger.error(f"VLLMEvaluator: Invalid response structure: {exc}")
            raise EvaluatorError(f"Invalid follow-up completion structure: {exc}")

        clean_content = content_str.strip()
        if clean_content.startswith("```"):
            clean_content = re.sub(r"^```(?:json)?\s*", "", clean_content)
            clean_content = re.sub(r"\s*```$", "", clean_content)

        try:
            parsed = json.loads(clean_content)
            return FollowUpQuestionPayload.model_validate(parsed)
        except Exception as exc:
            logger.error(f"VLLMEvaluator: Follow-up schema validation error: {exc}")
            raise EvaluatorError(f"Follow-up schema validation error: {exc}")
