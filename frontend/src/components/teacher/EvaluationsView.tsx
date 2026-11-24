import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { Assessment, FindingReviewStatus, Submission, SubmissionEvaluationSummary } from '../../types';

export const EvaluationsView: React.FC = () => {
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<number | ''>('');
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [selectedSubmissionId, setSelectedSubmissionId] = useState<number | ''>('');

  const [evalSummary, setEvalSummary] = useState<SubmissionEvaluationSummary | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [asyncStatusText, setAsyncStatusText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [reviewNote, setReviewNote] = useState<{ [findingId: number]: string }>({});

  useEffect(() => {
    const loadAssessments = async () => {
      try {
        const res = await api.getAssessments();
        setAssessments(res.items);
        if (res.items.length > 0) {
          setSelectedAssessmentId(res.items[0].id);
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
      if (res.items.length > 0) {
        setSelectedSubmissionId(res.items[0].id);
      } else {
        setSelectedSubmissionId('');
        setEvalSummary(null);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load submissions.');
    }
  };

  useEffect(() => {
    if (selectedSubmissionId) {
      loadEvaluations(Number(selectedSubmissionId));
    }
  }, [selectedSubmissionId]);

  const loadEvaluations = async (submissionId: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getSubmissionEvaluations(submissionId);
      setEvalSummary(res);
    } catch {
      // Might not have run evaluations yet
      setEvalSummary(null);
    } finally {
      setLoading(false);
    }
  };

  const handleRunEvaluation = async () => {
    if (!selectedSubmissionId) return;
    setEvaluating(true);
    setError(null);
    setSuccess(null);
    setAsyncStatusText('Queueing evaluation task in background worker...');
    try {
      const accepted = await api.triggerAsyncEvaluation(Number(selectedSubmissionId));
      if (accepted && accepted.task_id) {
        setAsyncStatusText('Processing OCR... Analyzing...');
        await api.pollTaskUntilComplete(
          accepted.task_id,
          (step) => setAsyncStatusText(step || 'Processing OCR... Analyzing...'),
          3000
        );
      }
      const res = await api.getSubmissionEvaluations(Number(selectedSubmissionId));
      setEvalSummary(res);
      setSuccess('AI Evaluation executed across approved student answers.');
    } catch (err: any) {
      setError(err.message || 'Evaluation failed. Ensure teacher-approved answers exist.');
    } finally {
      setEvaluating(false);
      setAsyncStatusText(null);
    }
  };

  const handleReviewFinding = async (findingId: number, status: FindingReviewStatus) => {
    setError(null);
    setSuccess(null);
    try {
      await api.reviewFinding(findingId, status, reviewNote[findingId]);
      setSuccess(`Finding #${findingId} marked as ${status}.`);
      if (selectedSubmissionId) loadEvaluations(Number(selectedSubmissionId));
    } catch (err: any) {
      setError(err.message || 'Failed to update finding review status.');
    }
  };

  return (
    <div>
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>AI Assessment & Misconception Evaluation</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          Execute diagnostic AI evaluation against teacher-approved answers and accept/reject identified misconceptions.
        </p>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      <div className="card" style={{ padding: '16px 20px', marginBottom: '20px', display: 'flex', gap: '20px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div>
          <label className="form-label" style={{ marginBottom: '6px' }}>Select Assessment</label>
          <select
            className="form-select"
            value={selectedAssessmentId}
            onChange={(e) => {
              setError(null);
              setSuccess(null);
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
              setSuccess(null);
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
            className="btn btn-primary"
            onClick={handleRunEvaluation}
            disabled={evaluating || !selectedSubmissionId}
          >
            {evaluating ? (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                <span className="spinner" />
                <span>{asyncStatusText || 'Evaluating...'}</span>
              </span>
            ) : (
              'Run Evaluation on Approved Answers'
            )}
          </button>
        </div>
      </div>

      <div className="alert alert-info" style={{ fontSize: '0.85rem' }}>
        <strong>Evaluation Foundation Note:</strong> The evaluation engine runs on a deterministic rule-based mock adapter. Accept findings to unlock targeted practice item generation.
      </div>

      {loading ? (
        <div className="loading-container">
          <span className="spinner" />
          <p>Loading evaluation runs...</p>
        </div>
      ) : !evalSummary || evalSummary.runs.length === 0 ? (
        <div className="card empty-state">
          No evaluations recorded yet for this submission. Click "Run Evaluation on Approved Answers" above.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="card" style={{ background: 'var(--bg-tertiary)', padding: '16px 20px' }}>
            <span style={{ fontWeight: 600 }}>Total Questions: {evalSummary.total_questions}</span> |{' '}
            <span style={{ color: 'var(--text-secondary)' }}>Evaluated Answers: {evalSummary.evaluated_count}</span> |{' '}
            <span style={{ color: 'var(--text-secondary)' }}>Evaluation Runs: {evalSummary.runs.length}</span>
          </div>

          {evalSummary.runs.map((run) => (
            <div key={run.id} className="card">
              <div className="card-header">
                <div>
                  <h3 className="card-title">Question #{run.question_id} Diagnostic Run</h3>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                    Evaluator: {run.evaluator_name} {run.is_cached && '(Cached Snapshot)'}
                  </div>
                </div>
                <span className="badge badge-neutral">Run #{run.id}</span>
              </div>

              <div style={{ background: 'var(--bg-primary)', padding: '10px 14px', borderRadius: 'var(--radius-sm)', marginBottom: '16px' }}>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
                  Student Authoritative Answer Snapshot:
                </div>
                <div style={{ fontFamily: 'monospace', fontSize: '0.92rem' }}>
                  {run.answer_text_snapshot}
                </div>
              </div>

              <h4 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '10px' }}>
                Identified Misconception Findings ({run.findings.length}):
              </h4>

              {run.findings.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.88rem' }}>
                  No conceptual misconceptions detected in this answer.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {run.findings.map((f) => (
                    <div
                      key={f.id}
                      style={{
                        background: 'var(--bg-primary)',
                        padding: '14px',
                        borderRadius: 'var(--radius-sm)',
                        border: '1px solid var(--border-color)',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <div>
                          <span style={{ fontWeight: 600, color: '#fca5a5' }}>
                            {f.concept_name ? `${f.concept_name}: ` : ''}{f.category || f.misconception_type || 'Misconception'}
                          </span>
                          {f.verdict && (
                            <span
                              className={`badge badge-${
                                f.verdict === 'correct'
                                  ? 'success'
                                  : f.verdict === 'partially_correct'
                                  ? 'warning'
                                  : f.verdict === 'incorrect'
                                  ? 'danger'
                                  : 'warning'
                              }`}
                              style={{ marginLeft: '8px', fontWeight: 600 }}
                            >
                              {f.verdict.toUpperCase().replace('_', ' ')}
                            </span>
                          )}
                          {f.marks_awarded !== undefined && f.marks_awarded !== null && (
                            <span style={{ marginLeft: '8px', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                              Marks: {f.marks_awarded} / {f.max_marks || 1}
                            </span>
                          )}
                          {f.error_amount && (
                            <span className="badge badge-danger" style={{ marginLeft: '8px' }}>
                              Error: {f.error_amount}
                            </span>
                          )}
                          <span style={{ marginLeft: '10px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                            Confidence: {(((f.confidence ?? f.confidence_score ?? 1.0)) * 100).toFixed(0)}%
                          </span>
                        </div>
                        <span className={`badge badge-${f.review_status === 'accepted' ? 'success' : f.review_status === 'rejected' ? 'danger' : 'warning'}`}>
                          {f.review_status}
                        </span>
                      </div>

                      {f.correct_answer && (
                        <div style={{ fontSize: '0.85rem', marginBottom: '6px', color: '#10b981' }}>
                          <strong>Model / Correct Answer: </strong>
                          <code>{f.correct_answer}</code>
                        </div>
                      )}

                      {(f.evidence_excerpt || f.evidence_quote) && (
                        <div style={{ fontSize: '0.85rem', marginBottom: '6px' }}>
                          <span style={{ color: 'var(--text-secondary)' }}>Evidence: </span>
                          <em>"{f.evidence_excerpt || f.evidence_quote}"</em>
                        </div>
                      )}

                      {f.step_by_step_explanation && (
                        <div style={{ fontSize: '0.85rem', background: 'var(--bg-secondary)', padding: '6px 10px', borderRadius: '4px', marginBottom: '6px' }}>
                          <strong>Step-by-Step Breakdown: </strong>{f.step_by_step_explanation}
                        </div>
                      )}

                      {(f.rationale || f.conceptual_explanation) && (
                        <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                          {f.rationale || f.conceptual_explanation}
                        </div>
                      )}

                      {f.misconception_hypothesis && (
                        <div style={{ fontSize: '0.82rem', color: '#f59e0b', marginBottom: '6px' }}>
                          <strong>Hypothesis: </strong><em>{f.misconception_hypothesis}</em>
                        </div>
                      )}

                      {(f.remediation_concept || f.follow_up_question) && (
                        <div style={{ fontSize: '0.82rem', color: '#818cf8', marginBottom: '8px' }}>
                          {f.remediation_concept && <div><strong>Remediation Target: </strong>{f.remediation_concept}</div>}
                          {f.follow_up_question && <div><strong>Verification Check: </strong><em>{f.follow_up_question}</em></div>}
                        </div>
                      )}

                      {f.uncertainty_rationale && (
                        <div style={{ fontSize: '0.82rem', color: '#fde68a', background: 'rgba(245, 158, 11, 0.08)', padding: '6px 10px', borderRadius: '4px', marginBottom: '10px' }}>
                          <strong>Uncertainty Note:</strong> {f.uncertainty_rationale}
                        </div>
                      )}

                      <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginTop: '10px', paddingTop: '10px', borderTop: '1px solid var(--border-color)' }}>
                        <input
                          type="text"
                          className="form-input"
                          placeholder="Teacher notes or rationale..."
                          style={{ flex: 1, padding: '6px 10px', fontSize: '0.85rem' }}
                          value={reviewNote[f.id] || ''}
                          onChange={(e) => setReviewNote({ ...reviewNote, [f.id]: e.target.value })}
                        />
                        <button
                          className="btn btn-success btn-sm"
                          onClick={() => handleReviewFinding(f.id, 'accepted')}
                          disabled={f.review_status === 'accepted'}
                        >
                          Accept
                        </button>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleReviewFinding(f.id, 'needs_revision')}
                        >
                          Flag
                        </button>
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => handleReviewFinding(f.id, 'rejected')}
                          disabled={f.review_status === 'rejected'}
                        >
                          Reject
                        </button>
                      </div>

                      {f.review_status === 'accepted' && (
                        <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'flex-end' }}>
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={async () => {
                              setError(null);
                              setSuccess(null);
                              try {
                                await api.generateRemediationsForFinding(f.id);
                                setSuccess(`Targeted practice items generated for Finding #${f.id}. View them in the Remediations tab.`);
                              } catch (err: any) {
                                setError(err.message || 'Failed to generate remediation items.');
                              }
                            }}
                          >
                            ⚡ Generate Practice Items
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
