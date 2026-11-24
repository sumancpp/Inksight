from typing import List
from app.core.logging import logger
from app.models.enums import FindingCategory, PracticeQuestionType, RemediationRunStatus
from app.schemas.remediation import PracticeItemOutput
from app.services.remediation_generator.base import (
    BaseRemediationGenerator,
    RemediationInput,
    RemediationResult,
)


class MockRemediationGenerator(BaseRemediationGenerator):
    """
    Deterministic mock implementation of targeted follow-up question generation.

    WARNING: This is a deterministic rule-based mock for testing and local development.
    It does NOT perform real AI/LLM generation or natural language reasoning.
    """

    name = "mock_remediation_generator"

    async def generate_practice(self, input_data: RemediationInput) -> RemediationResult:
        logger.info(
            f"MockRemediationGenerator: Generating practice for finding_id={input_data.finding_id}, "
            f"concept='{input_data.concept_name}', category='{input_data.finding_category.value}'"
        )

        # 1. Anti-hallucination guard: require sufficient question context
        has_prompt = bool(input_data.question_prompt and input_data.question_prompt.strip())
        has_grounding = bool(
            (input_data.rubric and input_data.rubric.strip())
            or (input_data.expected_answer and input_data.expected_answer.strip())
        )
        if not has_prompt or not has_grounding:
            logger.warning(
                f"MockRemediationGenerator: Insufficient context for finding_id={input_data.finding_id}. "
                "Refusing to fabricate practice questions."
            )
            return RemediationResult(
                status=RemediationRunStatus.INSUFFICIENT_CONTEXT,
                generator_name=self.name,
                items=[],
                error_message=(
                    "Insufficient context: question prompt or teacher rubric/expected answer is missing. "
                    "Cannot generate targeted practice without pedagogical grounding."
                ),
            )

        # 2. Safety guard: Never generate practice for insufficient evidence findings
        if input_data.finding_category == FindingCategory.INSUFFICIENT_EVIDENCE:
            return RemediationResult(
                status=RemediationRunStatus.INSUFFICIENT_CONTEXT,
                generator_name=self.name,
                items=[],
                error_message="Cannot generate remediation practice for an insufficient_evidence finding.",
            )

        # 3. Deterministic fixture mapping based on grounded concept and evidence
        concept_str = (input_data.concept_name or "").lower()
        evidence_str = (input_data.evidence_excerpt or "").lower()
        rationale_str = input_data.rationale.lower()
        prompt_str = input_data.question_prompt.lower()

        items: List[PracticeItemOutput] = []

        # Case A: Product rule misconception (e.g., student thought (fg)' = f' * g')
        if "product" in concept_str or "product rule" in rationale_str or "f' * g'" in evidence_str or "product" in prompt_str:
            items.append(
                PracticeItemOutput(
                    target_concept="product_rule",
                    question_text="Which of the following represents the correct derivative of the product h(x) = u(x) * v(x) according to the product rule?",
                    question_type=PracticeQuestionType.MULTIPLE_CHOICE,
                    options=[
                        "A) h'(x) = u'(x) * v'(x)",
                        "B) h'(x) = u'(x) * v(x) + u(x) * v'(x)",
                        "C) h'(x) = u'(x) + v'(x)",
                        "D) h'(x) = [u(x) + v(x)] * u'(x)",
                    ],
                    teacher_answer_key="B) h'(x) = u'(x) * v(x) + u(x) * v'(x)",
                    teacher_rationale="Directly targets the misconception where students multiply derivatives individually instead of applying the two-term Leibniz sum expansion.",
                    difficulty="easy",
                    uncertainty_note="Deterministic fixture for product rule misconception.",
                )
            )
            items.append(
                PracticeItemOutput(
                    target_concept="product_rule",
                    question_text="Let f(x) = x and g(x) = x^2. Evaluate the derivative of their product p(x) = x^3 using the power rule, then evaluate it using the product rule. Compare the two results and explain why (f*g)' is not equal to f' * g'.",
                    question_type=PracticeQuestionType.EXPLAIN_REASONING,
                    options=None,
                    teacher_answer_key="Power rule on x^3 gives 3x^2. If falsely using f'*g', we would get 1 * 2x = 2x != 3x^2. Using the product rule gives 1*(x^2) + x*(2x) = 3x^2, verifying the formula.",
                    teacher_rationale="Constructs an explicit numerical and algebraic counterexample so the student directly observes the mathematical failure of assuming (fg)' = f'g'.",
                    difficulty="medium",
                    uncertainty_note="Deterministic fixture for product rule conceptual counterexample.",
                )
            )

        # Case B: Power rule misconception or partial understanding
        elif "power" in concept_str or "power rule" in rationale_str or "power" in prompt_str:
            items.append(
                PracticeItemOutput(
                    target_concept="power_rule",
                    question_text="According to the power rule for differentiation, what is the derivative of f(x) = x^4 with respect to x?",
                    question_type=PracticeQuestionType.SHORT_ANSWER,
                    options=None,
                    teacher_answer_key="f'(x) = 4x^3",
                    teacher_rationale="Tests application of d/dx(x^n) = n*x^(n-1) to reinforce bringing the exponent down and subtracting one.",
                    difficulty="easy",
                    uncertainty_note="Deterministic fixture for power rule practice.",
                )
            )

        # Case C: Generic grounded practice item
        else:
            concept_display = input_data.concept_name or "the target topic"
            items.append(
                PracticeItemOutput(
                    target_concept=concept_display,
                    question_text=f"Explain in your own words how to solve a problem related to {concept_display}, detailing the key steps and common pitfalls to avoid.",
                    question_type=PracticeQuestionType.SHORT_ANSWER,
                    options=None,
                    teacher_answer_key=f"Expected criteria grounded in rubric: {input_data.rubric or input_data.expected_answer}",
                    teacher_rationale=f"Addresses identified gap regarding '{concept_display}' based on student evidence: '{input_data.evidence_excerpt or 'recorded response'}'.",
                    difficulty="medium",
                    uncertainty_note="Generic grounded practice item from mock generator.",
                )
            )

        return RemediationResult(
            status=RemediationRunStatus.COMPLETED,
            generator_name=self.name,
            items=items,
            error_message=None,
        )
