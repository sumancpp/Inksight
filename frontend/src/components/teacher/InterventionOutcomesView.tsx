import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { Assessment, InterventionOutcomesSummary, Submission } from '../../types';

interface InterventionOutcomesViewProps {
  initialSubmissionId?: number;
  initialAssessmentId?: number;
}

export const InterventionOutcomesView: React.FC<InterventionOutcomesViewProps> = ({
  initialSubmissionId,
  initialAssessmentId,
}) => {
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<number | ''>(initialAssessmentId ?? '');
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [selectedSubmissionId, setSelectedSubmissionId] = useState<number | ''>(initialSubmissionId ?? '');

  const [outcomesData, setOutcomesData] = useState<InterventionOutcomesSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadAssessments = async () => {
      try {
        const res = await api.getAssessments();
        setAssessments(res.items);
        if (res.items.length > 0 && !selectedAssessmentId) {
          const matchedAssessment = initialAssessmentId || res.items[0].id;
          setSelectedAssessmentId(matchedAssessment);
        }
      } catch (err: any) {
        setError(err.message || 'Failed to load assessments.');
      }
    };
    loadAssessments();
  }, []);

  useEffect(() => {
    if (selectedAssessmentId) {
      loadSubmissions(Number(selectedAssessmentId));
    }
  }, [selectedAssessmentId]);

  const loadSubmissions = async (assessmentId: number) => {
    try {
      const res = await api.getSubmissions(assessmentId);
      setSubmissions(res.items);
      if (initialSubmissionId && res.items.some((s) => s.id === initialSubmissionId)) {
        setSelectedSubmissionId(initialSubmissionId);
      } else if (res.items.length > 0) {
        if (!selectedSubmissionId || !res.items.some((s) => s.id === selectedSubmissionId)) {
          setSelectedSubmissionId(res.items[0].id);
        }
      } else {
        setSelectedSubmissionId('');
        setOutcomesData(null);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load submissions.');
    }
  };

  useEffect(() => {
    if (selectedSubmissionId) {
      loadOutcomes(Number(selectedSubmissionId));
    }
  }, [selectedSubmissionId]);

  const loadOutcomes = async (submissionId: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getSubmissionInterventionOutcomes(submissionId);
      setOutcomesData(res);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch intervention outcomes.');
      setOutcomesData(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Intervention Outcome Tracking & Learning Loop Verification</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          Verify whether instructional interventions resolved identified conceptual gaps by comparing prior assessment evidence with follow-up student practice.
        </p>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {/* Selectors */}
      <div className="card" style={{ padding: '16px 20px', marginBottom: '20px', display: 'flex', gap: '20px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div>
          <label className="form-label" style={{ marginBottom: '6px' }}>Select Assessment</label>
          <select
            className="form-select"
            value={selectedAssessmentId}
            onChange={(e) => {
              setError(null);
              setSelectedAssessmentId(Number(e.target.value));
            }}
          >
            {assessments.map((a) => (
              <option key={a.id} value={a.id}>
                {a.title} (ID #{a.id})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="form-label" style={{ marginBottom: '6px' }}>Select Submission</label>
          <select
            className="form-select"
            value={selectedSubmissionId}
            onChange={(e) => {
              setError(null);
              setSelectedSubmissionId(Number(e.target.value));
            }}
            disabled={submissions.length === 0}
          >
            {submissions.map((s) => (
              <option key={s.id} value={s.id}>
                Submission #{s.id} (Student #{s.student_id})
              </option>
            ))}
          </select>
        </div>

        <div>
          <button
            className="btn btn-secondary"
            onClick={() => selectedSubmissionId && loadOutcomes(Number(selectedSubmissionId))}
            disabled={loading || !selectedSubmissionId}
          >
            Refresh Outcomes
          </button>
        </div>
      </div>

      {loading ? (
        <div className="loading-container">
          <span className="spinner" />
          <p>Compiling intervention evidence and outcomes...</p>
        </div>
      ) : !outcomesData || outcomesData.outcomes.length === 0 ? (
        <div className="card empty-state">
          No intervention outcomes recorded for this submission yet. Verify that diagnostic findings have been accepted and follow-up practice items approved.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Summary Scorecard */}
          <div className="grid-4" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px' }}>
            <div className="card" style={{ padding: '14px 18px', background: 'var(--bg-tertiary)' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Tracked Interventions</div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700 }}>{outcomesData.total_interventions}</div>
            </div>
            <div className="card" style={{ padding: '14px 18px', background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--success)' }}>Demonstrated Improvement</div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--success)' }}>{outcomesData.improved_count}</div>
            </div>
            <div className="card" style={{ padding: '14px 18px', background: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.3)' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--warning)' }}>Uncertain (Need Evidence)</div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--warning)' }}>{outcomesData.uncertain_count}</div>
            </div>
            <div className="card" style={{ padding: '14px 18px', background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--danger)' }}>Persisting Gaps</div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--danger)' }}>{outcomesData.persisting_gap_count}</div>
            </div>
          </div>

          <div className="alert alert-info" style={{ fontSize: '0.85rem' }}>
            <strong>Pedagogical Integrity Note:</strong> {outcomesData.pedagogical_disclaimer}
          </div>

          {/* Intervention Details */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {outcomesData.outcomes.map((o) => {
              const statusBadgeClass =
                o.outcome_status === 'improved'
                  ? 'badge-success'
                  : o.outcome_status === 'uncertain'
                  ? 'badge-warning'
                  : o.outcome_status === 'persisting_gap'
                  ? 'badge-danger'
                  : 'badge-neutral';

              return (
                <div key={o.finding_id} className="card" style={{ padding: '18px' }}>
                  {/* Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', borderBottom: '1px solid var(--border-color)', paddingBottom: '10px' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <h3 className="card-title" style={{ fontSize: '1.1rem', margin: 0 }}>
                          {o.concept_name}
                        </h3>
                        {o.topic_name && <span className="badge badge-neutral">{o.topic_name}</span>}
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Question #{o.question_id}</span>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span className={`badge ${statusBadgeClass}`} style={{ fontSize: '0.85rem', padding: '6px 12px' }}>
                        {o.outcome_label}
                      </span>
                    </div>
                  </div>

                  {/* 3-Column Comparative Evidence Layout */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px', marginBottom: '16px' }}>
                    {/* Prior Diagnostic Baseline */}
                    <div style={{ background: 'var(--bg-primary)', padding: '14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem', color: '#fca5a5', marginBottom: '8px' }}>
                        1. Prior Diagnostic Baseline
                      </div>
                      <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
                        Type: <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{o.prior_category}</span> (Confidence: {(o.prior_confidence * 100).toFixed(0)}%)
                      </div>
                      {o.prior_evidence_excerpt && (
                        <div style={{ fontSize: '0.85rem', margin: '6px 0', background: 'var(--bg-secondary)', padding: '8px 10px', borderRadius: '4px' }}>
                          <span style={{ color: 'var(--text-secondary)' }}>Student Exam Answer: </span>
                          <em>"{o.prior_evidence_excerpt}"</em>
                        </div>
                      )}
                      {o.prior_rationale && (
                        <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                          {o.prior_rationale}
                        </div>
                      )}
                      {o.finding_review_notes && (
                        <div style={{ fontSize: '0.8rem', color: '#a5b4fc', marginTop: '6px' }}>
                          Teacher Review Note: {o.finding_review_notes}
                        </div>
                      )}
                    </div>

                    {/* Support Delivered */}
                    <div style={{ background: 'var(--bg-primary)', padding: '14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem', color: '#93c5fd', marginBottom: '8px' }}>
                        2. Support / Intervention Delivered
                      </div>
                      <div style={{ fontSize: '0.85rem', marginBottom: '8px' }}>
                        {o.support_summary}
                      </div>
                      <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                        Items Assigned: {o.remediation_items_count} teacher-approved exercise(s)
                      </div>
                    </div>

                    {/* Follow-up Evidence Collected */}
                    <div style={{ background: 'var(--bg-primary)', padding: '14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem', color: '#86efac', marginBottom: '8px' }}>
                        3. Follow-up Evidence Collected
                      </div>
                      <div style={{ fontSize: '0.85rem', marginBottom: '8px' }}>
                        {o.followup_summary}
                      </div>
                      {o.evidence_count > 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '180px', overflowY: 'auto' }}>
                          {o.followup_responses.map((resp, rIdx) => (
                            <div
                              key={rIdx}
                              style={{
                                background: 'var(--bg-secondary)',
                                padding: '8px 10px',
                                borderRadius: '4px',
                                borderLeft: `3px solid ${resp.is_correct ? 'var(--success)' : 'var(--danger)'}`,
                                fontSize: '0.82rem',
                              }}
                            >
                              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
                                <span>Attempt #{rIdx + 1} ({resp.item_question_type})</span>
                                <span className={`badge badge-${resp.is_correct ? 'success' : 'danger'}`} style={{ fontSize: '0.72rem' }}>
                                  {resp.is_correct ? 'Correct' : 'Incorrect'}
                                </span>
                              </div>
                              <div style={{ color: 'var(--text-secondary)' }}>
                                Answer: <em>"{resp.student_answer}"</em>
                              </div>
                              {resp.feedback && (
                                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                                  Feedback: {resp.feedback}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                          No responses recorded in practice sessions yet.
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Comparative Verdict & Recommended Action */}
                  <div
                    style={{
                      background: 'var(--bg-tertiary)',
                      padding: '12px 16px',
                      borderRadius: 'var(--radius-sm)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
                      <div style={{ fontSize: '0.88rem' }}>
                        <strong>Performance Comparison:</strong> {o.performance_comparison}
                      </div>
                      <div style={{ fontSize: '0.82rem' }}>
                        <span style={{ color: 'var(--text-secondary)' }}>Uncertainty Level: </span>
                        <span className={`badge badge-${o.uncertainty_level.includes('Low') ? 'success' : o.uncertainty_level.includes('High') ? 'warning' : 'info'}`}>
                          {o.uncertainty_level}
                        </span>
                      </div>
                    </div>

                    <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                      <strong>Uncertainty Note:</strong> {o.uncertainty_rationale}
                    </div>

                    <div style={{ fontSize: '0.85rem', color: '#93c5fd', marginTop: '4px', borderTop: '1px solid var(--border-color)', paddingTop: '6px' }}>
                      <strong>Recommended Teacher Action:</strong> {o.recommended_action}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
