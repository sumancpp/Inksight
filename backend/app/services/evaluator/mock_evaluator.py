import re
from typing import List, Optional

from app.core.logging import logger
from app.models.enums import FindingCategory, FollowUpQuestionType
from app.schemas.evaluation import ConfidenceDetails, FindingOutput, MisconceptionItem
from app.schemas.follow_up import FollowUpQuestionPayload, FollowUpRubric, RubricCriterion
from app.services.evaluator.base import (
    BaseEvaluator,
    EvaluationInput,
    EvaluationResult,
    FollowUpGenerationInput,
)


class MockEvaluator(BaseEvaluator):
    """
    Deterministic mock evaluator for local development and automated testing.
    Clearly labeled as mock. Implements strict safety rules:
    - Insufficient evidence if rubric or expected answer is missing.
    - Insufficient evidence if student answer is empty.
    - Deterministic categorization with concrete evidence excerpts and rationales.
    - Bounded confidence scores [0.0, 1.0].
    - Full diagnostic output: verdict, marks, error amount/type, step-by-step explanation, remediation.
    """

    @property
    def provider_name(self) -> str:
        return "mock_evaluator"

    async def evaluate(self, payload: EvaluationInput) -> EvaluationResult:
        logger.info(
            f"MockEvaluator: Evaluating answer for prompt='{payload.question_prompt[:40]}...'"
        )

        findings: List[FindingOutput] = []
        student_text = (payload.student_answer or "").strip()
        max_marks = float(payload.marks if payload.marks is not None else 1.0)

        # 0. Test Hook: Degraded evaluation trigger
        if "trigger_degraded" in student_text or "trigger_degraded" in (payload.question_prompt or ""):
            findings.append(
                FindingOutput(
                    concept_name=payload.topic_name or "Assessment Concept",
                    category=FindingCategory.INSUFFICIENT_EVIDENCE,
                    confidence=0.10,
                    uncertainty_rationale="Evaluator output degraded / invalid format.",
                    evidence_excerpt=None,
                    rationale="Evaluator output could not be validated against schema.",
                    verdict="needs_teacher_review",
                    correct_answer=payload.expected_answer,
                    marks_awarded=0.0,
                    max_marks=max_marks,
                    marks_reason="Degraded evaluation result awaiting teacher review.",
                    error_type="evaluator_degraded",
                    step_by_step_explanation="Automated evaluation encountered an unexpected format.",
                    misconceptions=[],
                    confidence_details=ConfidenceDetails(score=0.10, level="low", uncertainty_reasons=["evaluator_output_invalid"]),
                    requires_teacher_review=True,
                )
            )
            return EvaluationResult(evaluator_name=self.provider_name, findings=findings)

        # 1. Safety Rule: Empty student answer
        if not student_text:
            findings.append(
                FindingOutput(
                    concept_name=payload.topic_name or "Assessment Concept",
                    category=FindingCategory.INSUFFICIENT_EVIDENCE,
                    confidence=0.95,
                    uncertainty_rationale="No student text was submitted; conceptual understanding cannot be evaluated.",
                    evidence_excerpt=None,
                    rationale="The student answer is empty or whitespace-only. Cannot evaluate conceptual understanding without evidence.",
                    verdict="needs_teacher_review",
                    correct_answer=payload.expected_answer,
                    marks_awarded=0.0,
                    max_marks=max_marks,
                    marks_reason="No student text submitted; 0 marks awarded.",
                    error_type="unanswered",
                    step_by_step_explanation="The question was left blank. To answer, provide the steps and solution requested.",
                    misconceptions=[],
                    confidence_details=ConfidenceDetails(score=0.95, level="high", uncertainty_reasons=[]),
                    requires_teacher_review=False,
                    remediation_concept=payload.topic_name or "Core Topic Foundations",
                    follow_up_question=f"Can you attempt the first step of: {payload.question_prompt}?",
                )
            )
            return EvaluationResult(evaluator_name=self.provider_name, findings=findings)

        # 2. Safety Rule: Missing rubric and expected answer
        has_rubric = bool(payload.rubric and payload.rubric.strip())
        has_expected = bool(payload.expected_answer and payload.expected_answer.strip())
        if not has_rubric and not has_expected:
            findings.append(
                FindingOutput(
                    concept_name=payload.topic_name or "Rubric Requirement",
                    category=FindingCategory.INSUFFICIENT_EVIDENCE,
                    confidence=0.90,
                    uncertainty_rationale="Evaluation requires teacher-provided rubric criteria or expected model solution to prevent hallucination.",
                    evidence_excerpt=None,
                    rationale="The question lacks teacher-provided rubric criteria or expected model solution. The evaluation engine refrains from inventing grading standards.",
                    verdict="needs_teacher_review",
                    correct_answer=None,
                    marks_awarded=0.0,
                    max_marks=max_marks,
                    marks_reason="No rubric or expected answer provided; awaiting teacher review and approval of criteria.",
                    step_by_step_explanation="Cannot evaluate or grade student answer without an authoritative rubric or teacher-approved reference solution.",
                    misconceptions=[],
                    confidence_details=ConfidenceDetails(score=0.90, level="high", uncertainty_reasons=["missing_rubric_and_expected_answer"]),
                    requires_teacher_review=False,
                )
            )
            return EvaluationResult(evaluator_name=self.provider_name, findings=findings)

        # 3. Arithmetic Question Evaluation (e.g., "2 + 3 = ?", "2 + 3", or expected numerical answer)
        arith_prompt_match = re.search(
            r"(?:calculate|what is|\s*|^)\s*(\d+(?:\.\d+)?)\s*([\+\-\*\/])\s*(\d+(?:\.\d+)?)",
            payload.question_prompt,
            re.IGNORECASE,
        )
        if arith_prompt_match:
            op1_val = float(arith_prompt_match.group(1))
            op_str = arith_prompt_match.group(2)
            op2_val = float(arith_prompt_match.group(3))

            if op_str == "+":
                computed_ans = op1_val + op2_val
                op_verb = "adding"
            elif op_str == "-":
                computed_ans = op1_val - op2_val
                op_verb = "subtracting"
            elif op_str == "*":
                computed_ans = op1_val * op2_val
                op_verb = "multiplying"
            else:
                computed_ans = op1_val / op2_val if op2_val != 0 else 0.0
                op_verb = "dividing"

            student_num_match = re.search(r"[-+]?\d+(?:\.\d+)?", student_text)
            if student_num_match:
                student_num = float(student_num_match.group(0))
                diff = student_num - computed_ans

                fmt_c = int(computed_ans) if computed_ans.is_integer() else computed_ans
                fmt_s = int(student_num) if student_num.is_integer() else student_num
                fmt_op1 = int(op1_val) if op1_val.is_integer() else op1_val
                fmt_op2 = int(op2_val) if op2_val.is_integer() else op2_val

                if abs(diff) < 1e-9:
                    # Correct arithmetic answer
                    findings.append(
                        FindingOutput(
                            concept_name=payload.topic_name or "Arithmetic Addition",
                            category=FindingCategory.CORRECT_UNDERSTANDING,
                            confidence=0.98,
                            uncertainty_rationale="Exact numerical match with arithmetic computation.",
                            evidence_excerpt=student_num_match.group(0),
                            rationale=f"{fmt_op1} {op_str} {fmt_op2} correctly evaluated to {fmt_c}.",
                            verdict="correct",
                            correct_answer=str(fmt_c),
                            marks_awarded=max_marks,
                            max_marks=max_marks,
                            marks_reason=f"Correct calculation; awarded full {max_marks} marks.",
                            step_by_step_explanation=f"{fmt_op1} {op_str} {fmt_op2} equals {fmt_c}. The student's answer is correct.",
                            misconceptions=[],
                            confidence_details=ConfidenceDetails(score=0.98, level="high", uncertainty_reasons=[]),
                            requires_teacher_review=False,
                        )
                    )
                    return EvaluationResult(evaluator_name=self.provider_name, findings=findings)
                else:
                    # Incorrect arithmetic answer with error amount & step-by-step
                    diff_sign = "+" if diff > 0 else ""
                    diff_val = int(diff) if diff.is_integer() else round(diff, 2)
                    diff_str = f"{diff_sign}{diff_val}"
                    offset_desc = "one" if abs(diff) == 1 else str(abs(diff_val))
                    direction = "too high" if diff > 0 else "too low"
                    explanation = (
                        f"{fmt_op1} {op_str} {fmt_op2} means {op_verb} {fmt_op1} and {fmt_op2}, which gives {fmt_c}. "
                        f"The student wrote {fmt_s}, so the answer is {offset_desc} {direction}."
                    )
                    findings.append(
                        FindingOutput(
                            concept_name=payload.topic_name or "Arithmetic Addition",
                            category=FindingCategory.LIKELY_MISCONCEPTION,
                            confidence=0.95,
                            uncertainty_rationale="Deterministic arithmetic check identified exact calculation discrepancy.",
                            evidence_excerpt=student_num_match.group(0),
                            rationale=explanation,
                            verdict="incorrect",
                            correct_answer=str(fmt_c),
                            marks_awarded=0.0,
                            max_marks=max_marks,
                            marks_reason=f"Incorrect numerical result; 0 marks awarded out of {max_marks}.",
                            error_amount=diff_str,
                            error_type="arithmetic_calculation_error",
                            step_by_step_explanation=explanation,
                            misconceptions=[
                                MisconceptionItem(
                                    hypothesis="Counting error or arithmetic slip in single-digit computation.",
                                    evidence_excerpt=student_num_match.group(0),
                                    linked_concept=payload.topic_name or "Basic Addition & Arithmetic",
                                    severity="low",
                                )
                            ],
                            confidence_details=ConfidenceDetails(score=0.95, level="high", uncertainty_reasons=[]),
                            requires_teacher_review=False,
                            remediation_concept="Basic Addition & Arithmetic",
                            follow_up_question="What is 3 + 4 = ?",
                        )
                    )
                    return EvaluationResult(evaluator_name=self.provider_name, findings=findings)

        # 4. Deterministic Concept Rule Matching
        # Rule A: Known Misconception (Product rule confused with distributive derivative)
        misconception_patterns = [
            r"f'\s*\*\s*g'",
            r"f'\s*g'",
            r"\(f\*g\)'\s*=\s*f'g'",
            r"derivative of product is product of derivatives",
        ]
        matched_misc = None
        for pat in misconception_patterns:
            m = re.search(pat, student_text, re.IGNORECASE)
            if m:
                matched_misc = m.group(0)
                break

        if matched_misc:
            findings.append(
                FindingOutput(
                    concept_name="Product Rule",
                    category=FindingCategory.LIKELY_MISCONCEPTION,
                    confidence=0.92,
                    uncertainty_rationale="Student explicitly equates the derivative of a product to the product of derivatives.",
                    evidence_excerpt=matched_misc,
                    rationale="The student confuses the product rule with the sum rule of differentiation, mistakenly assuming that the derivative of a product is the product of individual derivatives (fg)' = f'g' rather than f'g + fg'.",
                    verdict="incorrect",
                    correct_answer=payload.expected_answer or "d/dx[f(x)*g(x)] = f'(x)g(x) + f(x)g'(x)",
                    marks_awarded=0.0,
                    max_marks=max_marks,
                    marks_reason="Product rule was erroneously applied as distributive derivative; 0 marks awarded.",
                    error_type="conceptual_rule_confusion",
                    step_by_step_explanation="Step 1: Identify product f(x)*g(x). Step 2: By the product rule, (fg)' = f'g + fg'. The student incorrectly wrote (fg)' = f'g', confusing product differentiation with sum differentiation.",
                    misconceptions=[
                        MisconceptionItem(
                            hypothesis="Distributive derivative misconception: assuming the derivative of a product equals the product of derivatives.",
                            evidence_excerpt=matched_misc,
                            linked_concept="Product Rule",
                            severity="high",
                        )
                    ],
                    confidence_details=ConfidenceDetails(score=0.92, level="high", uncertainty_reasons=[]),
                    requires_teacher_review=False,
                    remediation_concept="Product Rule of Differentiation",
                    follow_up_question="If u(x) = x and v(x) = sin(x), what is d/dx [u(x) * v(x)]?",
                )
            )
            return EvaluationResult(evaluator_name=self.provider_name, findings=findings)

        # Rule B: Partial understanding (Omission of inner derivative in chain rule)
        partial_patterns = [
            r"f'\s*\(\s*g\(x\)\s*\)(?!\s*\*\s*g')",
            r"forgot inner derivative",
            r"omits g'\(x\)",
        ]
        matched_partial = None
        for pat in partial_patterns:
            m = re.search(pat, student_text, re.IGNORECASE)
            if m:
                matched_partial = m.group(0)
                break

        if matched_partial:
            half_marks = round(max_marks * 0.5, 2)
            findings.append(
                FindingOutput(
                    concept_name="Chain Rule",
                    category=FindingCategory.PARTIALLY_CORRECT_UNDERSTANDING,
                    confidence=0.85,
                    uncertainty_rationale="Outer derivative is correctly identified, but inner derivative chain factor is omitted.",
                    evidence_excerpt=matched_partial,
                    rationale="The student successfully differentiated the outer function but omitted multiplying by the derivative of the inner function g'(x).",
                    verdict="partially_correct",
                    correct_answer=payload.expected_answer or "f'(g(x)) * g'(x)",
                    marks_awarded=half_marks,
                    max_marks=max_marks,
                    marks_reason=f"Partial credit ({half_marks}/{max_marks}) awarded: outer derivative identified, inner derivative chain factor missing.",
                    error_type="missing_step",
                    step_by_step_explanation="Step 1: Differentiate outer function f(u) to get f'(g(x)) [Correct]. Step 2: Multiply by inner derivative g'(x) by Chain Rule [Missing in student response].",
                    misconceptions=[
                        MisconceptionItem(
                            hypothesis="Incomplete chain rule: student stops after differentiating the outer function.",
                            evidence_excerpt=matched_partial,
                            linked_concept="Chain Rule",
                            severity="medium",
                        )
                    ],
                    confidence_details=ConfidenceDetails(score=0.85, level="high", uncertainty_reasons=[]),
                    requires_teacher_review=False,
                    remediation_concept="Chain Rule for Composite Functions",
                    follow_up_question="Differentiate h(x) = (2x + 5)^3 showing both outer and inner steps.",
                )
            )
            return EvaluationResult(evaluator_name=self.provider_name, findings=findings)

        # Rule C: Correct understanding
        correct_keywords = [
            "2x",
            "power rule",
            "f'g + fg'",
            "f'*g + f*g'",
            "rate of change",
            "limit is 1",
            "f'(g(x)) * g'(x)",
            "f'(g(x))*g'(x)",
        ]
        matched_correct = None
        for kw in correct_keywords:
            if kw.lower() in student_text.lower():
                idx = student_text.lower().find(kw.lower())
                matched_correct = student_text[idx : idx + len(kw)]
                break

        if matched_correct:
            findings.append(
                FindingOutput(
                    concept_name=payload.topic_name or "Core Mathematical Principle",
                    category=FindingCategory.CORRECT_UNDERSTANDING,
                    confidence=0.95,
                    uncertainty_rationale="Response matches rubric criteria and teacher model solution.",
                    evidence_excerpt=matched_correct,
                    rationale="The student accurately articulates the core mathematical relationship specified in the rubric and expected solution.",
                    verdict="correct",
                    correct_answer=payload.expected_answer or matched_correct,
                    marks_awarded=max_marks,
                    max_marks=max_marks,
                    marks_reason=f"Full marks ({max_marks}/{max_marks}) awarded for correct mathematical reasoning matching rubric.",
                    step_by_step_explanation="The student's solution demonstrates complete and correct procedural and conceptual understanding.",
                    misconceptions=[],
                    confidence_details=ConfidenceDetails(score=0.95, level="high", uncertainty_reasons=[]),
                    requires_teacher_review=False,
                )
            )
            return EvaluationResult(evaluator_name=self.provider_name, findings=findings)

        # Rule D: Descriptive Answer Evaluation against Rubric
        if has_rubric and payload.rubric:
            rubric_words = [w.lower() for w in re.findall(r"\b\w{4,}\b", payload.rubric)]
            student_words = [w.lower() for w in re.findall(r"\b\w{4,}\b", student_text)]
            matched_words = set(rubric_words).intersection(student_words)

            if len(matched_words) >= 3:
                sample_word = next(iter(matched_words))
                idx = student_text.lower().find(sample_word)
                excerpt = student_text[idx : idx + len(sample_word) + 20] if idx != -1 else student_text[:50]
                findings.append(
                    FindingOutput(
                        concept_name=payload.topic_name or "Descriptive Assessment Criteria",
                        category=FindingCategory.CORRECT_UNDERSTANDING,
                        confidence=0.88,
                        uncertainty_rationale="Student response substantively addresses core concepts defined in the grading rubric.",
                        evidence_excerpt=excerpt,
                        rationale="The response demonstrates clear alignment with key descriptive criteria outlined in the assessment rubric.",
                        verdict="correct",
                        correct_answer=payload.expected_answer or "Comprehensive explanation fulfilling rubric criteria.",
                        marks_awarded=max_marks,
                        max_marks=max_marks,
                        marks_reason=f"Full credit ({max_marks}/{max_marks}) awarded: response aligns with key rubric criteria.",
                        step_by_step_explanation="The student addresses all major aspects required by the scoring guide.",
                        misconceptions=[],
                        confidence_details=ConfidenceDetails(score=0.88, level="high", uncertainty_reasons=[]),
                        requires_teacher_review=False,
                    )
                )
                return EvaluationResult(evaluator_name=self.provider_name, findings=findings)
            elif len(matched_words) >= 1:
                half_marks = round(max_marks * 0.5, 2)
                sample_word = next(iter(matched_words))
                idx = student_text.lower().find(sample_word)
                excerpt = student_text[idx : idx + len(sample_word) + 20] if idx != -1 else student_text[:50]
                findings.append(
                    FindingOutput(
                        concept_name=payload.topic_name or "Descriptive Assessment Criteria",
                        category=FindingCategory.PARTIALLY_CORRECT_UNDERSTANDING,
                        confidence=0.80,
                        uncertainty_rationale="Student touches upon some rubric criteria but leaves out important depth or required terminology.",
                        evidence_excerpt=excerpt,
                        rationale="The response partially satisfies rubric requirements but lacks complete depth or evidence.",
                        verdict="partially_correct",
                        correct_answer=payload.expected_answer or "Complete descriptive solution addressing all rubric points.",
                        marks_awarded=half_marks,
                        max_marks=max_marks,
                        marks_reason=f"Partial credit ({half_marks}/{max_marks}) awarded for partial coverage of rubric criteria.",
                        error_type="incomplete_explanation",
                        step_by_step_explanation="The explanation touches upon key terms but lacks full analytical justification required by the rubric.",
                        misconceptions=[
                            MisconceptionItem(
                                hypothesis="Incomplete conceptual formulation of descriptive requirements.",
                                evidence_excerpt=excerpt,
                                linked_concept=payload.topic_name or "Descriptive Analysis",
                                severity="medium",
                            )
                        ],
                        confidence_details=ConfidenceDetails(score=0.80, level="medium", uncertainty_reasons=["partial_rubric_coverage"]),
                        requires_teacher_review=False,
                        remediation_concept=payload.topic_name or "Descriptive Analysis",
                        follow_up_question="Can you elaborate on how these principles apply to the full scenario?",
                    )
                )
                return EvaluationResult(evaluator_name=self.provider_name, findings=findings)

        # Rule E: Fallback when rubric is present but evidence is insufficient to diagnose
        first_sentence = student_text.split(".")[0].strip()
        excerpt = first_sentence[:60] if first_sentence else student_text[:60]
        findings.append(
            FindingOutput(
                concept_name=payload.topic_name or "General Concept",
                category=FindingCategory.INSUFFICIENT_EVIDENCE,
                confidence=0.45,
                uncertainty_rationale="Text does not contain recognizable conceptual markers matching rubric criteria or documented misconceptions.",
                evidence_excerpt=excerpt or None,
                rationale="The student response does not provide sufficient identifiable evidence to ascertain either correct understanding or a specific known misconception against the rubric.",
                verdict="needs_teacher_review",
                correct_answer=payload.expected_answer,
                marks_awarded=0.0,
                max_marks=max_marks,
                marks_reason="Insufficient evidence to grade automatically; teacher review required.",
                error_type="unrecognized_structure",
                step_by_step_explanation="The submitted response could not be verified automatically against the rubric criteria. A human teacher must review the answer.",
                misconceptions=[],
                confidence_details=ConfidenceDetails(score=0.45, level="low", uncertainty_reasons=["unrecognized_structure"]),
                requires_teacher_review=True,
                remediation_concept=payload.topic_name or "Concept Review",
                follow_up_question=f"Please re-explain your steps for: {payload.question_prompt[:60]}...",
            )
        )
        return EvaluationResult(evaluator_name=self.provider_name, findings=findings)

    async def generate_follow_up(self, payload: FollowUpGenerationInput) -> FollowUpQuestionPayload:
        if "trigger_ungrounded_followup" in payload.misconception_hypothesis:
            # Deliberately ungrounded concept to test 422 grounding check
            return FollowUpQuestionPayload(
                concept="Photosynthesis",
                question_text="Explain how light reactions generate ATP.",
                expected_answer="Light energy converts ADP to ATP.",
                rubric=FollowUpRubric(criteria=[RubricCriterion(text="Explains ATP production", marks=1.0)]),
                question_type=FollowUpQuestionType.SHORT_ANSWER,
            )

        if "trigger_hypothesis_grounding" in payload.misconception_hypothesis:
            return FollowUpQuestionPayload(
                concept="Quotient Rule",
                question_text="To test Quotient Rule, what is the derivative of f(x)/g(x)?",
                expected_answer="(f'g - fg') / g^2",
                rubric=FollowUpRubric(criteria=[RubricCriterion(text="Quotient Rule formula", marks=1.0)]),
                question_type=FollowUpQuestionType.SHORT_ANSWER,
            )

        concept = payload.linked_concept or "Targeted Concept"
        return FollowUpQuestionPayload(
            concept=concept,
            question_text=f"To verify your understanding of {concept}, what is the correct rule to apply when solving this type of problem?",
            expected_answer=f"Apply the canonical {concept} formula without conflating terms.",
            rubric=FollowUpRubric(
                criteria=[
                    RubricCriterion(text=f"Correctly states and applies the rule for {concept}", marks=1.0),
                ]
            ),
            question_type=FollowUpQuestionType.SHORT_ANSWER,
        )
