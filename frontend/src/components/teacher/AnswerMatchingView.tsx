import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { AnswerMatchingResponse, Assessment, ProposedAnswer, Question, Submission } from '../../types';

export const AnswerMatchingView: React.FC = () => {
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<number | ''>('');
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [selectedSubmissionId, setSelectedSubmissionId] = useState<number | ''>('');
  const [questions, setQuestions] = useState<Question[]>([]);

  const [matchingData, setMatchingData] = useState<AnswerMatchingResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Correction inline state
  const [correctingProposalId, setCorrectingProposalId] = useState<number | null>(null);
  const [correctedText, setCorrectedText] = useState('');
  const [correctedQuestionId, setCorrectedQuestionId] = useState<number | ''>('');

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
      loadSubmissionsAndQuestions(Number(selectedAssessmentId));
    }
  }, [selectedAssessmentId]);

  const loadSubmissionsAndQuestions = async (assessmentId: number) => {
    try {
      const [subsRes, qRes] = await Promise.all([
        api.getSubmissions(assessmentId),
        api.getQuestions(assessmentId),
      ]);
      setSubmissions(subsRes.items);
      setQuestions(qRes.items);
      if (subsRes.items.length > 0) {
        setSelectedSubmissionId(subsRes.items[0].id);
      } else {
        setSelectedSubmissionId('');
        setMatchingData(null);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load submissions.');
    }
  };

  useEffect(() => {
    if (selectedSubmissionId) {
      loadProposals(Number(selectedSubmissionId));
    }
  }, [selectedSubmissionId]);

  const loadProposals = async (submissionId: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getProposedAnswers(submissionId);
      setMatchingData(res);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch proposed answer matches.');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (proposalId: number) => {
    setError(null);
    setSuccess(null);
    try {
      await api.approveProposal(proposalId);
      setSuccess(`Proposal #${proposalId} approved and recorded to authoritative answer.`);
      if (selectedSubmissionId) loadProposals(Number(selectedSubmissionId));
    } catch (err: any) {
      setError(err.message || 'Failed to approve proposal.');
    }
  };

  const handleReject = async (proposalId: number) => {
    const reason = window.prompt('Reason for rejecting proposal (optional):', 'Excluded by instructor');
    if (reason === null) return; // User cancelled
    setError(null);
    setSuccess(null);
    try {
      await api.rejectProposal(proposalId, reason);
      setSuccess(`Proposal #${proposalId} rejected.`);
      if (selectedSubmissionId) loadProposals(Number(selectedSubmissionId));
    } catch (err: any) {
      setError(err.message || 'Failed to reject proposal.');
    }
  };

  const handleStartCorrect = (p: ProposedAnswer) => {
    setCorrectingProposalId(p.id);
    setCorrectedText(p.proposed_text);
    setCorrectedQuestionId(p.question_id || '');
  };

  const handleSaveCorrection = async (proposalId: number) => {
    if (!correctedText.trim() || !correctedQuestionId) return;
    setError(null);
    setSuccess(null);
    try {
      await api.correctProposal(proposalId, Number(correctedQuestionId), correctedText, 'Teacher manual correction');
      setSuccess(`Proposal #${proposalId} corrected and approved.`);
      setCorrectingProposalId(null);
      if (selectedSubmissionId) loadProposals(Number(selectedSubmissionId));
    } catch (err: any) {
      setError(err.message || 'Failed to correct proposal.');
    }
  };

  return (
    <div>
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Answer Matching & Teacher Review</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          Review OCR segment proposals matched to assessment questions. Approve, correct, or reject matches.
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
          <p>Loading matching proposals...</p>
        </div>
      ) : !matchingData ? (
        <div className="empty-state">Select a submission to review matching proposals.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Summary Banner */}
          <div className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-tertiary)' }}>
            <div>
              <span style={{ fontWeight: 600 }}>Matched: {matchingData.matched_count}</span> |{' '}
              <span style={{ color: 'var(--text-secondary)' }}>
                Unmatched Segments: {(matchingData.unmatched_segment_ids || matchingData.unmatched_segments || []).length}
              </span> |{' '}
              <span style={{ color: 'var(--text-secondary)' }}>
                Unanswered Questions: {(matchingData.unanswered_question_ids || matchingData.unanswered_questions || []).length}
              </span>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={() => loadProposals(Number(selectedSubmissionId))}>
              Refresh Matching
            </button>
          </div>

          {/* Proposals List */}
          <div className="card">
            <h3 className="card-title" style={{ marginBottom: '16px' }}>
              Proposed Answers ({matchingData.proposals.length})
            </h3>

            {matchingData.proposals.length === 0 ? (
              <div className="empty-state">No proposed answers found for this submission.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                {matchingData.proposals.map((p) => {
                  const targetQ = questions.find((q) => q.id === p.question_id);
                  const isEditing = correctingProposalId === p.id;
                  const conf = p.confidence ?? p.confidence_score ?? 0;
                  const statusClass =
                    p.status === 'approved'
                      ? 'badge-success'
                      : p.status === 'corrected'
                      ? 'badge-info'
                      : p.status === 'rejected'
                      ? 'badge-danger'
                      : 'badge-warning';

                  return (
                    <div
                      key={p.id}
                      style={{
                        background: 'var(--bg-primary)',
                        padding: '16px',
                        borderRadius: 'var(--radius-sm)',
                        border: '1px solid var(--border-color)',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <div>
                          <span style={{ fontWeight: 600 }}>
                            Target: {targetQ ? targetQ.prompt : (p.question_id ? `Question #${p.question_id}` : 'Unassigned (No Question Matched)')}
                          </span>
                          <span style={{ marginLeft: '10px', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                            ({(conf * 100).toFixed(0)}% OCR Character Confidence)
                          </span>
                        </div>
                        <span className={`badge ${statusClass}`}>
                          {p.status}
                        </span>
                      </div>

                      {p.corrected_text && (
                        <div style={{ background: 'rgba(99, 102, 241, 0.08)', borderLeft: '3px solid var(--primary)', padding: '6px 10px', borderRadius: '0 4px 4px 0', marginBottom: '8px', fontSize: '0.88rem' }}>
                          <span style={{ color: '#a5b4fc', fontWeight: 600 }}>Corrected Text: </span>
                          <span style={{ fontFamily: 'monospace' }}>{p.corrected_text}</span>
                        </div>
                      )}

                      {/* Status Advisory / Rejection / Unmatched explanation */}
                      {p.status === 'rejected' && (
                        <div style={{ background: 'rgba(239, 68, 68, 0.1)', borderLeft: '3px solid var(--danger)', padding: '6px 10px', borderRadius: '0 4px 4px 0', marginBottom: '8px', fontSize: '0.85rem', color: '#fca5a5' }}>
                          <strong>Rejected by Instructor:</strong> {p.rejection_reason || 'Excluded from assessment'}
                        </div>
                      )}

                      {p.status === 'unmatched' && (
                        <div style={{ background: 'rgba(148, 163, 184, 0.12)', borderLeft: '3px solid #94a3b8', padding: '6px 10px', borderRadius: '0 4px 4px 0', marginBottom: '8px', fontSize: '0.85rem', color: '#cbd5e1' }}>
                          <strong>Unmatched Proposal:</strong>{' '}
                          {p.rejection_reason === 'QUESTION_NUMBER_OUT_OF_BOUNDS'
                            ? 'The detected question number is outside the bounds of this assessment. Reassign to an existing question using "Correct / Reassign" or reject if extraneous.'
                            : p.rejection_reason === 'NO_QUESTION_NUMBER_DETECTED'
                            ? 'No question number could be identified in this OCR segment. Assign to a question using "Correct / Reassign".'
                            : p.rejection_reason?.startsWith('SUPERSEDED_')
                            ? 'Superseded by another approved proposal for this question.'
                            : p.rejection_reason || 'Unmatched segment requiring manual question assignment.'}
                        </div>
                      )}

                      {p.status === 'needs_review' && p.rejection_reason && (
                        <div style={{ background: 'rgba(245, 158, 11, 0.12)', borderLeft: '3px solid #f59e0b', padding: '6px 10px', borderRadius: '0 4px 4px 0', marginBottom: '8px', fontSize: '0.85rem', color: '#fcd34d' }}>
                          <strong>Teacher Review Advisory:</strong>{' '}
                          {p.rejection_reason === 'EXISTING_ANSWER_PRESENT'
                            ? 'An answer is already recorded for this question. Approving will replace the existing submission response.'
                            : p.rejection_reason === 'DUPLICATE_QUESTION_NUMBER'
                            ? 'Multiple OCR segments matched this question number. Review and approve the correct student answer.'
                            : p.rejection_reason === 'LOW_OCR_CONFIDENCE'
                            ? 'Low character recognition confidence detected. Please verify before approving.'
                            : p.rejection_reason}
                        </div>
                      )}

                      {isEditing ? (
                        <div style={{ marginTop: '12px', background: 'var(--bg-secondary)', padding: '14px', borderRadius: 'var(--radius-sm)' }}>
                          <div className="form-group">
                            <label className="form-label">Assign to Assessment Question</label>
                            <select
                              className="form-select"
                              value={correctedQuestionId}
                              onChange={(e) => setCorrectedQuestionId(Number(e.target.value))}
                            >
                              <option value="">-- Select Question --</option>
                              {questions.map((q) => (
                                <option key={q.id} value={q.id}>
                                  Q{q.id}: {q.prompt}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="form-group">
                            <label className="form-label">Corrected Answer Text</label>
                            <textarea
                              className="form-textarea"
                              value={correctedText}
                              onChange={(e) => setCorrectedText(e.target.value)}
                            />
                          </div>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <button className="btn btn-success btn-sm" onClick={() => handleSaveCorrection(p.id)}>
                              Save & Approve Correction
                            </button>
                            <button className="btn btn-secondary btn-sm" onClick={() => setCorrectingProposalId(null)}>
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div style={{ background: 'var(--bg-secondary)', padding: '10px 14px', borderRadius: 'var(--radius-sm)', marginBottom: '12px' }}>
                            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
                              OCR Proposed Text:
                            </div>
                            <div style={{ fontFamily: 'monospace', fontSize: '0.92rem' }}>
                              {p.proposed_text}
                            </div>
                          </div>

                          <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                            <button
                              className="btn btn-success btn-sm"
                              onClick={() => handleApprove(p.id)}
                              disabled={p.status === 'approved' || p.status === 'rejected' || !p.question_id}
                              title={!p.question_id ? 'Unmatched proposal must be assigned to an assessment question before approval' : 'Approve proposal as authoritative answer'}
                            >
                              {p.status === 'approved' ? '✓ Approved' : 'Approve'}
                            </button>
                            <button
                              className="btn btn-secondary btn-sm"
                              onClick={() => handleStartCorrect(p)}
                            >
                              Correct / Reassign
                            </button>
                            <button
                              className="btn btn-danger btn-sm"
                              onClick={() => handleReject(p.id)}
                              disabled={p.status === 'rejected'}
                            >
                              {p.status === 'rejected' ? 'Rejected' : 'Reject'}
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
