import pytest
from app.models.enums import PracticeItemReviewStatus, PracticeQuestionType
from app.models.remediation import RemediationItem
from app.services.practice_service import practice_service


@pytest.fixture
def mcq_item():
    """Remediation item with Multiple Choice format."""
    return RemediationItem(
        id=101,
        finding_id=1,
        run_id=1,
        target_concept="Chain Rule",
        question_text="What is the derivative of f(g(x))?",
        question_type=PracticeQuestionType.MULTIPLE_CHOICE.value,
        options=["A) f'(g(x)) * g'(x)", "B) f'(g'(x))", "C) f'(x) * g'(x)", "D) f(g'(x))"],
        teacher_answer_key="A",
        review_status=PracticeItemReviewStatus.APPROVED.value,
    )


@pytest.fixture
def mcq_item_full_text():
    """Remediation item where the teacher answer key includes the option letter and text."""
    return RemediationItem(
        id=102,
        finding_id=1,
        run_id=1,
        target_concept="Product Rule",
        question_text="Select the correct Leibniz product rule formula:",
        question_type=PracticeQuestionType.MULTIPLE_CHOICE.value,
        options=["A) u'v + uv'", "B) u'v'", "C) uv' - u'v"],
        teacher_answer_key="A) u'v + uv'",
        review_status=PracticeItemReviewStatus.APPROVED.value,
    )


@pytest.fixture
def short_answer_item():
    """Remediation item with Short Answer format."""
    return RemediationItem(
        id=103,
        finding_id=1,
        run_id=1,
        target_concept="Derivatives",
        question_text="What is the derivative of 2x^2 at x = 1?",
        question_type=PracticeQuestionType.SHORT_ANSWER.value,
        teacher_answer_key="4",
        review_status=PracticeItemReviewStatus.APPROVED.value,
    )


@pytest.fixture
def explain_reasoning_item():
    """Remediation item with Explain Reasoning format."""
    return RemediationItem(
        id=104,
        finding_id=1,
        run_id=1,
        target_concept="Product Rule",
        question_text="Explain why (u*v)' does not equal u' * v'.",
        question_type=PracticeQuestionType.EXPLAIN_REASONING.value,
        teacher_answer_key="The difference quotient requires intermediate terms when expanding the limit of the product.",
        review_status=PracticeItemReviewStatus.APPROVED.value,
    )


# -------------------------------------------------------------------------
# 1. Multiple Choice (MCQ) Scoring Tests
# -------------------------------------------------------------------------

def test_mcq_case_whitespace_and_punctuation(mcq_item):
    """MCQ should handle case insensitivity, surrounding whitespace, and punctuation formatting."""
    valid_answers = [
        "a",
        "A",
        " A ",
        "A.",
        "a.",
        "A)",
        "a)",
        "(A)",
        "(a)",
        "Option A",
        "option a",
        "Choice A",
        "choice a",
    ]
    for ans in valid_answers:
        is_correct, score, feedback = practice_service.grade_answer(mcq_item, ans)
        assert is_correct is True, f"Failed for valid answer: {ans!r}"
        assert score == 1.0
        assert "Correct!" in feedback


def test_mcq_matching_full_text_key(mcq_item_full_text):
    """When the answer key is 'A) u'v + uv'', single letter 'A' or 'Option A' must match."""
    for ans in ["A", "a", "A)", "Option A", "A) u'v + uv'"]:
        is_correct, score, _ = practice_service.grade_answer(mcq_item_full_text, ans)
        assert is_correct is True, f"Failed for answer: {ans!r}"
        assert score == 1.0


def test_mcq_prevents_false_positives(mcq_item):
    """
    CRITICAL FALSE-POSITIVE PREVENTION:
    Words starting with letter 'a' (like 'apple' or 'all') must NOT be evaluated as choice A.
    """
    false_answers = [
        "apple",
        "addition",
        "all of the above",
        "anything",
        "answer",
        "B",
        "C",
        "D",
        "Option B",
    ]
    for ans in false_answers:
        is_correct, score, feedback = practice_service.grade_answer(mcq_item, ans)
        assert is_correct is False, f"False positive occurred for: {ans!r}"
        assert score == 0.0
        assert "Incorrect" in feedback


# -------------------------------------------------------------------------
# 2. Short Answer Scoring Tests
# -------------------------------------------------------------------------

def test_short_answer_normalization_and_whitespace(short_answer_item):
    """Short answer should match normalized input regardless of surrounding whitespace or case."""
    valid_answers = [
        "4",
        " 4 ",
        "4.0",
        "The answer is 4",
        "It equals 4",
    ]
    for ans in valid_answers:
        is_correct, score, _ = practice_service.grade_answer(short_answer_item, ans)
        assert is_correct is True, f"Failed for answer: {ans!r}"
        assert score == 1.0


def test_short_answer_word_boundary_prevents_substring_false_positives(short_answer_item):
    """
    Word '4' must NOT match '14', '40', '44', or 'twenty-four'.
    """
    false_answers = [
        "14",
        "40",
        "44",
        "400",
        "twenty-four",
        "fourteen",
    ]
    for ans in false_answers:
        is_correct, score, feedback = practice_service.grade_answer(short_answer_item, ans)
        assert is_correct is False, f"False positive substring match occurred for: {ans!r}"
        assert score == 0.0


def test_short_answer_negation_detection(short_answer_item):
    """Answers explicitly stating negative statements before the target must be graded incorrect."""
    negated_answers = [
        "not 4",
        "never 4",
        "it is not 4",
        "cannot be 4",
        "isn't 4",
    ]
    for ans in negated_answers:
        is_correct, score, _ = practice_service.grade_answer(short_answer_item, ans)
        assert is_correct is False, f"False positive occurred for negated answer: {ans!r}"
        assert score == 0.0


def test_short_answer_excessive_length_rejection(short_answer_item):
    """Prompt dumping or excessively long paragraphs containing the answer must be rejected."""
    long_answer = "Here is an essay about mathematics where I will list numbers 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 to try to fool keyword grading."
    is_correct, score, _ = practice_service.grade_answer(short_answer_item, long_answer)
    assert is_correct is False
    assert score == 0.0


# -------------------------------------------------------------------------
# 3. Explain Reasoning Scoring Tests
# -------------------------------------------------------------------------

def test_explain_reasoning_length_boundary(explain_reasoning_item):
    """
    Boundary length check:
    Answers < 15 characters are rejected regardless of content.
    Answers >= 15 characters with target terminology are accepted.
    """
    # 14 chars -> Too brief
    short_ans = "limit expands."  # 14 chars
    is_correct, score, feedback = practice_service.grade_answer(explain_reasoning_item, short_ans)
    assert is_correct is False
    assert score == 0.0
    assert "too brief" in feedback.lower()

    # 15+ chars with keywords -> Accepted
    valid_ans = "The limit expands intermediate cross terms."  # >15 chars
    is_correct, score, feedback = practice_service.grade_answer(explain_reasoning_item, valid_ans)
    assert is_correct is True
    assert score == 1.0


def test_explain_reasoning_non_answer_refusal(explain_reasoning_item):
    """
    CRITICAL: Non-answers, ignorance, or refusals must NOT be scored as correct
    even if they contain concept keywords and exceed 15 characters.
    """
    non_answers = [
        "I do not know the answer for product rule.",
        "I don't know how to explain this difference quotient.",
        "I have no idea about intermediate terms or limits.",
        "Not sure at all about the product rule.",
        "idk how to explain the product rule formula.",
        "I cannot explain this difference quotient.",
        "I do not understand why intermediate terms appear.",
    ]
    for ans in non_answers:
        is_correct, score, feedback = practice_service.grade_answer(explain_reasoning_item, ans)
        assert is_correct is False, f"False positive occurred for non-answer: {ans!r}"
        assert score == 0.0
        assert "uncertainty" in feedback.lower() or "revision" in feedback.lower()


def test_explain_reasoning_whole_word_matching_prevents_substring_confusion(explain_reasoning_item):
    """
    Word 'term' must NOT match 'intermediate' or 'determine'.
    """
    # Contains 'determine' (which contains substring 'term'), but not the word 'term' itself
    # and no other matching keywords
    misleading = "We can determine and calculate the derivative function."
    is_correct, score, _ = practice_service.grade_answer(explain_reasoning_item, misleading)
    assert is_correct is False
    assert score == 0.0


def test_explain_reasoning_repetition_attack(explain_reasoning_item):
    """
    Repeating a single keyword multiple times must NOT satisfy the requirement
    for multiple distinct concept/answer keywords.
    """
    repetition = "product product product product product product"
    is_correct, score, _ = practice_service.grade_answer(explain_reasoning_item, repetition)
    assert is_correct is False
    assert score == 0.0


def test_explain_reasoning_stopwords_ignored(explain_reasoning_item):
    """
    Common stopwords ('that', 'with', 'from', 'have', etc.) must not count toward conceptual matches.
    """
    stopword_heavy = "I have that with this from there and then about."
    is_correct, score, _ = practice_service.grade_answer(explain_reasoning_item, stopword_heavy)
    assert is_correct is False
    assert score == 0.0


# -------------------------------------------------------------------------
# 4. Global Empty / Missing Answer Handling
# -------------------------------------------------------------------------

def test_empty_and_whitespace_only_answers_all_types(mcq_item, short_answer_item, explain_reasoning_item):
    """Empty and whitespace strings across all question types must immediately return False, 0.0."""
    empty_samples = ["", " ", "   ", "\t", "\n", " \t \n "]
    for item in [mcq_item, short_answer_item, explain_reasoning_item]:
        for empty in empty_samples:
            is_correct, score, feedback = practice_service.grade_answer(item, empty)
            assert is_correct is False
            assert score == 0.0
            assert "no answer provided" in feedback.lower()
