import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { Assessment, EvaluationFinding, RemediationItemTeacherRead, RemediationReviewStatus, Submission } from '../../types';

export const RemediationsView: React.FC = () => {
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<number | ''>('');
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [selectedSubmissionId, setSelectedSubmissionId] = useState<number | ''>('');

  const [acceptedFindings, setAcceptedFindings] = useState<EvaluationFinding[]>([]);
  const [items, setItems] = useState<RemediationItemTeacherRead[]>([]);

  const [generating, setGenerating] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Edit item inline state
  const [editingItemId, setEditingItemId] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const [editAnswer, setEditAnswer] = useState('');
  const [editExplanation, setEditExplanation] = useState('');

  // Transitive resolution helpers: read active teacher corrections first, falling back to original fields
  const resolveFindingConcept = (f: EvaluationFinding): string | null => {
    const activeCorr = f.corrections?.find(
      (c) => c.field_name === 'linked_concept' && c.status === 'active'
    );
    if (activeCorr?.corrected_value) {
      return String(activeCorr.corrected_value);
    }
    return f.concept_name || f.misconceptions?.[0]?.linked_concept || f.remediation_concept || null;
  };

  const resolveFindingEvidence = (f: EvaluationFinding): string | null => {
    const activeCorr = f.corrections?.find(
      (c) => c.field_name === 'evidence_excerpt' && c.status === 'active'
    );
    if (activeCorr?.corrected_value) {
      return String(activeCorr.corrected_value);
    }
    return f.evidence_excerpt || f.evidence_quote || f.misconceptions?.[0]?.evidence_excerpt || null;
  };

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
        setItems([]);
        setAcceptedFindings([]);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load submissions.');
    }
  };

  useEffect(() => {
    if (selectedSubmissionId) {
      loadData(Number(selectedSubmissionId));
    }
  }, [selectedSubmissionId]);

  const loadData = async (submissionId: number) => {
    setLoading(true);
    setError(null);
    try {
      const [evalRes, itemsRes] = await Promise.all([
        api.getSubmissionEvaluations(submissionId).catch(() => null),
        api.getRemediationItemsForSubmission(submissionId).catch(() => []),
      ]);

      if (evalRes) {
        const accepted: EvaluationFinding[] = [];
        evalRes.runs.forEach((r) => {
          r.findings.forEach((f) => {
            if (f.review_status === 'accepted') {
              accepted.push(f);
            }
          });
        });
        setAcceptedFindings(accepted);
      } else {
        setAcceptedFindings([]);
      }

      setItems(itemsRes);
    } catch (err: any) {
      setError(err.message || 'Failed to load remediation items.');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async (findingId: number) => {
    setGenerating(true);
    setError(null);
    setSuccess(null);
    try {
      await api.generateRemediationsForFinding(findingId);
      setSuccess('Targeted remediation practice items generated.');
      if (selectedSubmissionId) loadData(Number(selectedSubmissionId));
    } catch (err: any) {
      setError(err.message || 'Failed to generate remediations for finding.');
    } finally {
      setGenerating(false);
    }
  };

  const handleReviewItem = async (itemId: number, status: RemediationReviewStatus) => {
    setError(null);
    setSuccess(null);
    try {
      await api.reviewRemediationItem(itemId, status);
      setSuccess(`Practice item #${itemId} set to ${status}.`);
      if (selectedSubmissionId) loadData(Number(selectedSubmissionId));
    } catch (err: any) {
      setError(err.message || 'Failed to review practice item.');
    }
  };

  const handleStartEdit = (item: RemediationItemTeacherRead) => {
    setEditingItemId(item.id);
    setEditText(item.edited_question_text || item.question_text || item.prompt || '');
    setEditAnswer(item.edited_answer_key || item.teacher_answer_key || item.expected_answer || '');
    setEditExplanation(item.review_notes || item.teacher_rationale || item.explanation || '');
  };

  const handleSaveEdit = async (itemId: number) => {
    if (!editText.trim()) {
      setError("Question prompt cannot be empty.");
      return;
    }
    setError(null);
    setSuccess(null);
    try {
      await api.reviewRemediationItem(itemId, 'edited', {
        edited_question_text: editText.trim(),
        edited_answer_key: editAnswer.trim() || undefined,
        review_notes: editExplanation.trim() || undefined,
      });
      await api.reviewRemediationItem(itemId, 'approved');
      setSuccess(`Practice item #${itemId} edited and approved for student delivery.`);
      setEditingItemId(null);
      if (selectedSubmissionId) loadData(Number(selectedSubmissionId));
    } catch (err: any) {
      setError(err.message || 'Failed to save edits.');
    }
  };

  return (
    <div>
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Remediation Generation & Teacher Approval</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          Generate follow-up practice items for accepted misconceptions. Only approved items are delivered to students.
        </p>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      <div className="card" style={{ padding: '16px 20px', marginBottom: '20px', display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
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
      </div>

      {loading ? (
        <div className="loading-container">
          <span className="spinner" />
          <p>Loading remediations...</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Accepted Findings Section */}
          <div className="card">
            <h3 className="card-title" style={{ marginBottom: '14px' }}>
              Accepted Misconception Findings ({acceptedFindings.length})
            </h3>

            {acceptedFindings.length === 0 ? (
              <div className="empty-state">
                No accepted findings found for this submission. Go to the "AI Evaluation" tab and accept findings first.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {acceptedFindings.map((f) => {
                  const resolvedConcept = resolveFindingConcept(f);
                  const resolvedEvidence = resolveFindingEvidence(f);

                  return (
                    <div
                      key={f.id}
                      data-testid={`finding-row-${f.id}`}
                      style={{
                        background: 'var(--bg-primary)',
                        padding: '12px 16px',
                        borderRadius: 'var(--radius-sm)',
                        border: '1px solid var(--border-color)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <div>
                        <div
                          data-testid={`finding-concept-${f.id}`}
                          style={{ fontWeight: 600, color: '#fca5a5' }}
                        >
                          {resolvedConcept ? `${resolvedConcept}: ` : ''}{f.category || f.misconception_type || 'Misconception'}
                        </div>
                        <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                          Finding #{f.id} | Evidence: <em>"{resolvedEvidence || 'N/A'}"</em>
                          {f.acknowledged_uncertainty && (
                            <span className="badge badge-warning" style={{ marginLeft: '8px', fontSize: '0.72rem' }}>
                              Uncertainty Acknowledged
                            </span>
                          )}
                        </div>
                      </div>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => handleGenerate(f.id)}
                        disabled={generating}
                      >
                        {generating ? <span className="spinner" /> : 'Generate Practice Items'}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Generated Practice Items Review */}
          <div className="card">
            <h3 className="card-title" style={{ marginBottom: '16px' }}>
              Generated Remediation Items ({items.length})
            </h3>

            {items.length === 0 ? (
              <div className="empty-state">
                No remediation items generated yet. Click "Generate Practice Items" on an accepted finding above.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {items.map((item) => {
                  const isEditing = editingItemId === item.id;
                  const parentFinding = acceptedFindings.find((f) => f.id === item.finding_id);
                  const targetConcept = item.target_concept || (parentFinding ? resolveFindingConcept(parentFinding) : null);

                  return (
                    <div
                      key={item.id}
                      data-testid={`remediation-item-card-${item.id}`}
                      style={{
                        background: 'var(--bg-primary)',
                        padding: '16px',
                        borderRadius: 'var(--radius-sm)',
                        border: '1px solid var(--border-color)',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <div>
                          <span style={{ fontWeight: 600 }}>Item #{item.id}</span>
                          <span style={{ marginLeft: '10px', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                            Type: <strong>{item.question_type}</strong> | Finding #{item.finding_id}
                          </span>
                          {targetConcept && (
                            <span
                              data-testid={`remediation-target-concept-${item.id}`}
                              style={{ marginLeft: '10px', fontSize: '0.82rem', color: '#93c5fd' }}
                            >
                              Concept: <strong>{targetConcept}</strong>
                            </span>
                          )}
                        </div>
                        <span className={`badge badge-${item.review_status === 'approved' || item.review_status === 'edited' ? 'success' : item.review_status === 'rejected' ? 'danger' : 'warning'}`}>
                          {item.review_status}
                        </span>
                      </div>

                      {isEditing ? (
                        <div style={{ background: 'var(--bg-secondary)', padding: '14px', borderRadius: 'var(--radius-sm)', marginTop: '10px' }}>
                          <div className="form-group">
                            <label className="form-label">Question Text</label>
                            <textarea
                              className="form-textarea"
                              value={editText}
                              onChange={(e) => setEditText(e.target.value)}
                            />
                          </div>
                          <div className="form-group">
                            <label className="form-label">Expected Answer</label>
                            <input
                              type="text"
                              className="form-input"
                              value={editAnswer}
                              onChange={(e) => setEditAnswer(e.target.value)}
                            />
                          </div>
                          <div className="form-group">
                            <label className="form-label">Teacher Explanation</label>
                            <textarea
                              className="form-textarea"
                              value={editExplanation}
                              onChange={(e) => setEditExplanation(e.target.value)}
                            />
                          </div>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <button className="btn btn-success btn-sm" onClick={() => handleSaveEdit(item.id)}>
                              Save Edits & Approve
                            </button>
                            <button className="btn btn-secondary btn-sm" onClick={() => setEditingItemId(null)}>
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div style={{ marginBottom: '10px', fontSize: '0.95rem' }}>
                            {item.edited_question_text || item.question_text || item.prompt}
                          </div>

                          {item.options && (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '12px' }}>
                              {item.options.map((opt, oIdx) => (
                                <div key={oIdx} style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                                  • {opt}
                                </div>
                              ))}
                            </div>
                          )}

                          <div style={{ background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)', padding: '10px 14px', borderRadius: 'var(--radius-sm)', marginBottom: '12px', fontSize: '0.85rem' }}>
                            <div style={{ marginBottom: '4px' }}>
                              <span style={{ fontSize: '0.78rem', color: '#a5b4fc', fontWeight: 600 }}>🔒 Instructor Verification (Protected from Students)</span>
                            </div>
                            <div>
                              <strong style={{ color: 'var(--success)' }}>Expected Answer Key:</strong>{' '}
                              <code>{item.edited_answer_key || item.teacher_answer_key || item.edited_expected_answer || item.expected_answer}</code>
                            </div>
                            <div style={{ marginTop: '4px', color: 'var(--text-secondary)' }}>
                              <strong>Teacher Rationale:</strong> {item.review_notes || item.teacher_rationale || item.edited_explanation || item.explanation}
                            </div>
                          </div>

                          <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                            <button
                              className="btn btn-success btn-sm"
                              onClick={() => handleReviewItem(item.id, 'approved')}
                              disabled={item.review_status === 'approved'}
                            >
                              Approve for Delivery
                            </button>
                            <button
                              className="btn btn-secondary btn-sm"
                              onClick={() => handleStartEdit(item)}
                            >
                              Edit & Approve
                            </button>
                            <button
                              className="btn btn-danger btn-sm"
                              onClick={() => handleReviewItem(item.id, 'rejected')}
                              disabled={item.review_status === 'rejected'}
                            >
                              Reject
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
