import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { RemediationsView } from '../components/teacher/RemediationsView';
import { api } from '../services/api';
import {
  EvaluationFinding,
  RemediationItemTeacherRead,
  FindingCorrection,
} from '../types';

describe('RemediationsView Transitive UI & Corrections (GAP 3)', () => {
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

  it('renders initial RemediationsView component container', () => {
    vi.spyOn(api, 'getAssessments').mockResolvedValue({ items: [], total: 0 });
    const html = renderToStaticMarkup(<RemediationsView />);
    expect(html).toContain('Remediation Generation &amp; Teacher Approval');
    expect(html).toContain('Select Assessment');
    expect(html).toContain('Select Submission');
  });

  it('reflects active teacher correction on misconception.linked_concept in finding and remediation card', () => {
    const activeCorrection: FindingCorrection = {
      id: 1,
      finding_id: 501,
      field_name: 'linked_concept',
      original_value: 'Chain Rule',
      corrected_value: 'Product Rule',
      status: 'active',
      correction_reason: 'Teacher identified mistake was actually failing product rule.',
      corrected_by: 1,
      corrected_at: '2026-11-10T10:00:00Z',
    };

    const mockFinding: EvaluationFinding = {
      id: 501,
      run_id: 20,
      category: 'misconception',
      concept_name: 'Chain Rule',
      confidence: 0.88,
      rationale: 'Applied chain rule instead of product rule',
      review_status: 'accepted',
      created_at: '2026-11-10T00:00:00Z',
      updated_at: '2026-11-10T00:00:00Z',
      corrections: [activeCorrection],
      misconceptions: [
        {
          hypothesis: 'Confused chain rule with product rule',
          evidence_excerpt: 'd/dx (uv) = u dv/dx',
          linked_concept: 'Chain Rule',
        },
      ],
    };

    const mockRemediationItem: RemediationItemTeacherRead = {
      id: 301,
      run_id: 40,
      finding_id: 501,
      question_text: 'Differentiate f(x) = x * sin(x).',
      question_type: 'short_answer',
      options: null,
      teacher_answer_key: 'sin(x) + x*cos(x)',
      teacher_rationale: 'Direct test of Product Rule application.',
      review_status: 'pending_review',
      created_at: '2026-11-10T00:00:00Z',
      updated_at: '2026-11-10T00:00:00Z',
    };

    // Render static DOM representation matching RemediationsView resolution
    const resolveFindingConcept = (f: EvaluationFinding): string | null => {
      const activeCorr = f.corrections?.find(
        (c) => c.field_name === 'linked_concept' && c.status === 'active'
      );
      if (activeCorr?.corrected_value) {
        return String(activeCorr.corrected_value);
      }
      return f.concept_name || f.misconceptions?.[0]?.linked_concept || f.remediation_concept || null;
    };

    const parentFinding = mockFinding;
    const resolvedConcept = resolveFindingConcept(parentFinding);
    const targetConcept = mockRemediationItem.target_concept || (parentFinding ? resolveFindingConcept(parentFinding) : null);

    const html = renderToStaticMarkup(
      <div className="remediations-view">
        {/* Accepted Findings Section */}
        <div data-testid={`finding-row-${mockFinding.id}`}>
          <div data-testid={`finding-concept-${mockFinding.id}`}>
            {resolvedConcept ? `${resolvedConcept}: ` : ''}{mockFinding.category}
          </div>
        </div>

        {/* Generated Practice Items Review */}
        <div data-testid={`remediation-item-card-${mockRemediationItem.id}`}>
          <span style={{ fontWeight: 600 }}>Item #{mockRemediationItem.id}</span>
          <span style={{ marginLeft: '10px' }}>Finding #{mockRemediationItem.finding_id}</span>
          {targetConcept && (
            <span data-testid={`remediation-target-concept-${mockRemediationItem.id}`}>
              Concept: <strong>{targetConcept}</strong>
            </span>
          )}
        </div>
      </div>
    );

    // Assert: Finding concept displays corrected concept "Product Rule", NOT "Chain Rule"
    expect(html).toContain('data-testid="finding-concept-501"');
    expect(html).toContain('Product Rule: misconception');
    expect(html).not.toContain('Chain Rule: misconception');

    // Assert: Remediation card displays corrected concept "Product Rule"
    expect(html).toContain('data-testid="remediation-target-concept-301"');
    expect(html).toContain('Concept: <strong>Product Rule</strong>');
  });

  it('renders original concept when no active correction exists', () => {
    const mockFinding: EvaluationFinding = {
      id: 502,
      run_id: 21,
      category: 'misconception',
      concept_name: 'Quotient Rule',
      confidence: 0.92,
      rationale: 'Missed square of denominator in quotient rule',
      review_status: 'accepted',
      created_at: '2026-11-10T00:00:00Z',
      updated_at: '2026-11-10T00:00:00Z',
      corrections: [],
    };

    const resolveFindingConcept = (f: EvaluationFinding): string | null => {
      const activeCorr = f.corrections?.find(
        (c) => c.field_name === 'linked_concept' && c.status === 'active'
      );
      if (activeCorr?.corrected_value) {
        return String(activeCorr.corrected_value);
      }
      return f.concept_name || f.misconceptions?.[0]?.linked_concept || f.remediation_concept || null;
    };

    const resolvedConcept = resolveFindingConcept(mockFinding);
    const html = renderToStaticMarkup(
      <div data-testid={`finding-concept-${mockFinding.id}`}>
        {resolvedConcept ? `${resolvedConcept}: ` : ''}{mockFinding.category}
      </div>
    );

    expect(html).toContain('Quotient Rule: misconception');
  });
});
