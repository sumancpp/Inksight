import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { EvaluationFindingCard, getCategoryBadgeClass } from '../components/evaluation/EvaluationFindingCard';
import { EvaluationFinding, FindingCorrection, FollowUpQuestion } from '../types';
import { api } from '../services/api';

describe('EvaluationFindingCard Component & Review Gate Tests', () => {
  const store: Record<string, string> = {};
  const mockLocalStorage = {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      for (const k of Object.keys(store)) delete store[k];
    },
  };

  beforeEach(() => {
    vi.stubGlobal('localStorage', mockLocalStorage);
    mockLocalStorage.clear();
    vi.restoreAllMocks();
  });

  const baseFinding: EvaluationFinding = {
    id: 101,
    concept_name: 'Product Rule Differentiation',
    category: 'likely_misconception',
    confidence: 0.85,
    verdict: 'incorrect',
    marks_awarded: 0,
    max_marks: 5,
    review_status: 'pending_review',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    rationale: 'Student treated derivative of product as product of derivatives.',
    step_by_step_explanation: 'Step 1: (fg)\' = f\'g + fg\'. Student wrote f\'g\'.',
    misconceptions: [
      {
        hypothesis: 'Distributive derivative error',
        evidence_excerpt: "f'g'",
        linked_concept: 'Product Rule',
        severity: 'high',
      },
    ],
    confidence_details: {
      score: 0.85,
      level: 'high',
      uncertainty_reasons: [],
    },
    requires_teacher_review: false,
  };

  it('renders grounded misconceptions with hypothesis, excerpt, and severity', () => {
    const html = renderToStaticMarkup(
      <EvaluationFindingCard
        finding={baseFinding}
        ocrConfidence={0.92}
        onReview={vi.fn()}
      />
    );

    expect(html).toContain('Distributive derivative error');
    expect(html).toContain("f&#x27;g&#x27;"); // escaped quote in static markup
    expect(html).toContain('Product Rule');
    expect(html).toContain('high severity');
    expect(html).toContain('OCR Confidence:');
    expect(html).toContain('92%');
    expect(html).toContain('Diagnostic Confidence:');
    expect(html).toContain('85%');
    expect(html).toContain('high');
  });

  it('displays low-confidence review gate banner and disables accept when requires_teacher_review is true', () => {
    const lowConfidenceFinding: EvaluationFinding = {
      ...baseFinding,
      confidence: 0.40,
      confidence_details: {
        score: 0.40,
        level: 'low',
        uncertainty_reasons: ['unrecognized_structure', 'no_grounded_misconception_evidence'],
      },
      requires_teacher_review: true,
    };

    const html = renderToStaticMarkup(
      <EvaluationFindingCard
        finding={lowConfidenceFinding}
        ocrConfidence={0.88}
        onReview={vi.fn()}
      />
    );

    expect(html).toContain('Review Gate: Low Diagnostic Confidence');
    expect(html).toContain('I acknowledge the diagnostic uncertainty');
    expect(html).toContain('unrecognized structure');
    expect(html).toContain('no grounded misconception evidence');
    // Accept button has disabled attribute initially because acknowledgment checkbox is unchecked
    expect(html).toContain('disabled=""');
  });

  it('api.reviewFinding transmits acknowledge_uncertainty flag accurately', async () => {
    let capturedBody: any = null;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url: RequestInfo | URL, init?: RequestInit) => {
      capturedBody = JSON.parse(init?.body as string);
      return new Response(JSON.stringify({ ...baseFinding, review_status: 'accepted' }), { status: 200 });
    });

    // 1. When acknowledgeUncertainty is true
    await api.reviewFinding(101, 'accepted', 'Teacher approved with uncertainty', true);
    expect(capturedBody).toEqual({
      action: 'accepted',
      review_notes: 'Teacher approved with uncertainty',
      acknowledge_uncertainty: true,
    });

    // 2. When acknowledgeUncertainty is false
    await api.reviewFinding(101, 'accepted', 'Teacher standard approval', false);
    expect(capturedBody).toEqual({
      action: 'accepted',
      review_notes: 'Teacher standard approval',
      acknowledge_uncertainty: false,
    });
  });

  it('getCategoryBadgeClass maps categories correctly', () => {
    expect(getCategoryBadgeClass('correct_understanding')).toBe('badge-success');
    expect(getCategoryBadgeClass('likely_misconception')).toBe('badge-danger');
    expect(getCategoryBadgeClass('partially_correct_understanding')).toBe('badge-warning');
    expect(getCategoryBadgeClass('insufficient_evidence')).toBe('badge-neutral');
  });

  it('teacher clicks Accept -> backend returns 422 -> UI shows error toast/banner with the backend detail message', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      return new Response(
        JSON.stringify({ detail: 'Low-confidence finding requires explicit acknowledgement.' }),
        { status: 422, statusText: 'Unprocessable Content', headers: { 'Content-Type': 'application/json' } }
      );
    });

    let bannerMessage: string | null = null;
    let bannerType: string | null = null;

    const handleReviewWithUIBanner = async (
      findingId: number,
      action: any,
      notes?: string,
      ack?: boolean
    ) => {
      try {
        await api.reviewFinding(findingId, action, notes, ack);
      } catch (err: any) {
        bannerType = 'error';
        bannerMessage = err.message || 'Failed to update finding';
      }
    };

    // Teacher triggers review without acknowledgement
    await handleReviewWithUIBanner(101, 'accepted', 'Approving without check', false);

    expect(bannerType).toBe('error');
    expect(bannerMessage).toBe('Low-confidence finding requires explicit acknowledgement.');

    // Render the UI error banner as in DemoDashboard
    const bannerHtml = renderToStaticMarkup(
      <div className={`alert alert-${bannerType}`}>
        <div>{bannerMessage}</div>
      </div>
    );
    expect(bannerHtml).toContain('alert-error');
    expect(bannerHtml).toContain('Low-confidence finding requires explicit acknowledgement.');
  });

  it('Follow-up verification button disabled logic enforced when unaccepted, low-confidence unacknowledged, or no misconceptions', () => {
    // Case 1: unaccepted (pending_review)
    const unacceptedFinding: EvaluationFinding = {
      ...baseFinding,
      review_status: 'pending_review',
      misconceptions: [
        {
          hypothesis: 'Confused product rule with sum',
          evidence_excerpt: "f'(x) = 2x",
          linked_concept: 'Product Rule',
          severity: 'high',
        },
      ],
    };
    const htmlUnaccepted = renderToStaticMarkup(
      <EvaluationFindingCard finding={unacceptedFinding} onReview={() => {}} />
    );
    expect(htmlUnaccepted).toContain('data-testid="generate-follow-up-btn"');
    expect(htmlUnaccepted).toMatch(/<button[^>]*disabled[^>]*data-testid="generate-follow-up-btn"|<button[^>]*data-testid="generate-follow-up-btn"[^>]*disabled/);

    // Case 2: low confidence and not acknowledged
    const unackFinding: EvaluationFinding = {
      ...baseFinding,
      review_status: 'accepted',
      requires_teacher_review: true,
      acknowledged_uncertainty: false,
      misconceptions: [
        {
          hypothesis: 'Confused product rule with sum',
          evidence_excerpt: "f'(x) = 2x",
          linked_concept: 'Product Rule',
          severity: 'high',
        },
      ],
    };
    const htmlUnack = renderToStaticMarkup(
      <EvaluationFindingCard finding={unackFinding} onReview={() => {}} />
    );
    expect(htmlUnack).toMatch(/<button[^>]*disabled[^>]*data-testid="generate-follow-up-btn"|<button[^>]*data-testid="generate-follow-up-btn"[^>]*disabled/);

    // Case 3: no misconceptions
    const noMiscFinding: EvaluationFinding = {
      ...baseFinding,
      review_status: 'accepted',
      misconceptions: [],
      misconception_hypothesis: undefined,
    };
    const htmlNoMisc = renderToStaticMarkup(
      <EvaluationFindingCard finding={noMiscFinding} onReview={() => {}} />
    );
    expect(htmlNoMisc).toMatch(/<button[^>]*disabled[^>]*data-testid="generate-follow-up-btn"|<button[^>]*data-testid="generate-follow-up-btn"[^>]*disabled/);
  });

  it('Follow-up verification button is enabled when accepted with grounded misconceptions', () => {
    const acceptedFinding: EvaluationFinding = {
      ...baseFinding,
      review_status: 'accepted',
      requires_teacher_review: false,
      misconceptions: [
        {
          hypothesis: 'Confused product rule with sum',
          evidence_excerpt: "f'(x) = 2x",
          linked_concept: 'Product Rule',
          severity: 'high',
        },
      ],
    };
    const html = renderToStaticMarkup(
      <EvaluationFindingCard finding={acceptedFinding} onReview={() => {}} />
    );
    expect(html).toContain('data-testid="generate-follow-up-btn"');
    // Button should NOT have disabled attribute
    expect(html).not.toMatch(/data-testid="generate-follow-up-btn"[^>]*disabled/);
  });

  it('Follow-up API calls: propose, approve, reject, and 422 error handling', async () => {
    // 1. Mock propose
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(async () => {
      return new Response(
        JSON.stringify({
          id: 55,
          finding_id: 101,
          assessment_id: 1,
          concept: 'Product Rule',
          question_text: 'What is the product rule for differentiation?',
          expected_answer: "f'g + fg'",
          rubric: { criteria: [{ text: 'States formula', marks: 1.0 }] },
          question_type: 'short_answer',
          status: 'proposed',
          proposed_by: 'system',
          created_at: new Date().toISOString(),
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    });

    const proposed = await api.proposeFollowUp(101);
    expect(proposed.id).toBe(55);
    expect(proposed.status).toBe('proposed');
    expect(proposed.concept).toBe('Product Rule');

    // 2. Mock approve
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(async () => {
      return new Response(
        JSON.stringify({
          ...proposed,
          status: 'approved',
          approved_by: 1,
          approved_at: new Date().toISOString(),
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    });

    const approved = await api.approveFollowUp(55, 'Looks good');
    expect(approved.status).toBe('approved');
    expect(approved.approved_by).toBe(1);

    // 3. Mock 422 grounding failure
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(async () => {
      return new Response(
        JSON.stringify({ detail: 'Generated follow-up failed grounding: concept Photosynthesis does not match.' }),
        { status: 422, statusText: 'Unprocessable Content', headers: { 'Content-Type': 'application/json' } }
      );
    });

    await expect(api.proposeFollowUp(101)).rejects.toThrow('Generated follow-up failed grounding');
  });

  it('Follow-up expected_answer is collapsed by default in the UI', () => {
    const sampleFollowUp: FollowUpQuestion = {
      id: 99,
      finding_id: 101,
      assessment_id: 1,
      concept: 'Product Rule',
      question_text: 'Differentiate f(x) = x * ln(x)',
      expected_answer: 'ln(x) + 1',
      rubric: { criteria: [{ text: 'Product rule formula applied', marks: 1.0 }] },
      question_type: 'short_answer',
      status: 'proposed',
      proposed_by: 'system',
      created_at: new Date().toISOString(),
    };

    const acceptedFinding: EvaluationFinding = {
      ...baseFinding,
      review_status: 'accepted',
      requires_teacher_review: false,
      misconceptions: [
        {
          hypothesis: 'Confused product rule',
          evidence_excerpt: "f'(x) = 2x",
          linked_concept: 'Product Rule',
          severity: 'high',
        },
      ],
    };

    const html = renderToStaticMarkup(
      <EvaluationFindingCard
        finding={acceptedFinding}
        initialFollowUps={[sampleFollowUp]}
        onReview={() => {}}
      />
    );

    // Initial render must show "Show Expected Answer" toggle button
    expect(html).toContain('Show Expected Answer ▼');
    // Expected answer text MUST be collapsed / hidden by default (not in DOM)
    expect(html).not.toContain('ln(x) + 1');
    expect(html).not.toContain('data-testid="follow-up-expected-answer-99"');
  });

  it('Follow-up status badge renders correctly for all three states (PROPOSED, APPROVED, REJECTED)', () => {
    const makeFollowUp = (status: 'proposed' | 'approved' | 'rejected'): FollowUpQuestion => ({
      id: 100,
      finding_id: 101,
      assessment_id: 1,
      concept: 'Product Rule',
      question_text: 'Differentiate f(x) = x * e^x',
      expected_answer: 'e^x + x * e^x',
      rubric: { criteria: [{ text: 'Product rule', marks: 1.0 }] },
      question_type: 'short_answer',
      status,
      proposed_by: 'system',
      created_at: new Date().toISOString(),
    });

    const acceptedFinding: EvaluationFinding = {
      ...baseFinding,
      review_status: 'accepted',
      requires_teacher_review: false,
      misconceptions: [
        {
          hypothesis: 'Confused product rule',
          evidence_excerpt: "f'(x) = 2x",
          linked_concept: 'Product Rule',
          severity: 'high',
        },
      ],
    };

    // 1. Proposed state
    const htmlProposed = renderToStaticMarkup(
      <EvaluationFindingCard
        finding={acceptedFinding}
        initialFollowUps={[makeFollowUp('proposed')]}
        onReview={() => {}}
      />
    );
    expect(htmlProposed).toContain('data-testid="follow-up-status-badge-100"');
    expect(htmlProposed).toContain('proposed');
    expect(htmlProposed).toContain('badge-warning');

    // 2. Approved state
    const htmlApproved = renderToStaticMarkup(
      <EvaluationFindingCard
        finding={acceptedFinding}
        initialFollowUps={[makeFollowUp('approved')]}
        onReview={() => {}}
      />
    );
    expect(htmlApproved).toContain('data-testid="follow-up-status-badge-100"');
    expect(htmlApproved).toContain('approved');
    expect(htmlApproved).toContain('badge-success');

    // 3. Rejected state
    const htmlRejected = renderToStaticMarkup(
      <EvaluationFindingCard
        finding={acceptedFinding}
        initialFollowUps={[makeFollowUp('rejected')]}
        onReview={() => {}}
      />
    );
    expect(htmlRejected).toContain('data-testid="follow-up-status-badge-100"');
    expect(htmlRejected).toContain('rejected');
    expect(htmlRejected).toContain('badge-danger');
  });

  it('Teacher correction: renders teacher_corrected badge when finding has teacher_corrected true or active corrections', () => {
    // Case 1: finding marked teacher_corrected
    const correctedFinding: EvaluationFinding = {
      ...baseFinding,
      teacher_corrected: true,
    };
    const html1 = renderToStaticMarkup(
      <EvaluationFindingCard finding={correctedFinding} onReview={() => {}} />
    );
    expect(html1).toContain('data-testid="teacher-corrected-badge"');
    expect(html1).toContain('Teacher Corrected');

    // Case 2: active correction in initialCorrections
    const activeCorr: FindingCorrection = {
      id: 1,
      finding_id: 101,
      field_name: 'linked_concept',
      original_value: 'Chain Rule',
      corrected_value: 'Product Rule',
      correction_reason: 'Pedagogical refinement',
      status: 'active',
      corrected_at: new Date().toISOString(),
    };
    const html2 = renderToStaticMarkup(
      <EvaluationFindingCard
        finding={baseFinding}
        initialCorrections={[activeCorr]}
        onReview={() => {}}
      />
    );
    expect(html2).toContain('data-testid="teacher-corrected-badge"');
  });

  it('Teacher correction: renders original and corrected values side-by-side with revert button', () => {
    const activeCorr: FindingCorrection = {
      id: 2,
      finding_id: 101,
      field_name: 'misconception_hypothesis',
      original_value: 'AI guessed wrong rule',
      corrected_value: 'Teacher confirmed specific algebraic confusion',
      correction_reason: 'Fixed diagnosis',
      status: 'active',
      corrected_at: new Date().toISOString(),
    };

    const findingWithMisc: EvaluationFinding = {
      ...baseFinding,
      misconceptions: [
        {
          hypothesis: 'AI guessed wrong rule',
          evidence_excerpt: "f'(x) = 2x",
          linked_concept: 'Product Rule',
          severity: 'high',
        },
      ],
    };

    const html = renderToStaticMarkup(
      <EvaluationFindingCard
        finding={findingWithMisc}
        initialCorrections={[activeCorr]}
        onReview={() => {}}
      />
    );

    // Shows active corrected value in strong
    expect(html).toContain('Teacher confirmed specific algebraic confusion');
    // Shows original in del
    expect(html).toContain('<del>AI guessed wrong rule</del>');
    // Shows reason
    expect(html).toContain('Fixed diagnosis');
    // Shows revert button
    expect(html).toContain('data-testid="revert-correction-btn-misconception_hypothesis"');
  });

  it('Teacher correction API client: apply and revert', async () => {
    // 1. Mock apply
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(async () => {
      return new Response(
        JSON.stringify({
          id: 12,
          finding_id: 101,
          field_name: 'linked_concept',
          original_value: 'Chain Rule',
          corrected_value: 'Product Rule',
          correction_reason: 'Correction reason',
          status: 'active',
          corrected_at: new Date().toISOString(),
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    });

    const corr = await api.applyCorrection(101, 'linked_concept', 'Product Rule', 'Correction reason');
    expect(corr.id).toBe(12);
    expect(corr.status).toBe('active');
    expect(corr.corrected_value).toBe('Product Rule');

    // 2. Mock revert
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(async () => {
      return new Response(
        JSON.stringify({
          ...corr,
          status: 'reverted',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    });

    const rev = await api.revertCorrection(101, 12);
    expect(rev.status).toBe('reverted');
  });
});
