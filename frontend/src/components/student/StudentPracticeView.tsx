import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import {
  Assessment,
  PracticeSessionSummary,
  StudentPracticeItemRead,
  StudentPracticeSessionRead,
  StudentProgressReport,
} from '../../types';

export const StudentPracticeView: React.FC = () => {
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<number | ''>('');

  const [session, setSession] = useState<StudentPracticeSessionRead | null>(null);
  const [summary, setSummary] = useState<PracticeSessionSummary | null>(null);

  const [answers, setAnswers] = useState<{ [itemId: number]: string }>({});
  const [submittingItemId, setSubmittingItemId] = useState<number | null>(null);

  const [submissions, setSubmissions] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Student Learning Loop & Outcome Tracking State
  const [progressReport, setProgressReport] = useState<StudentProgressReport | null>(null);
  const [loadingReport, setLoadingReport] = useState<boolean>(false);
  const [showReport, setShowReport] = useState<boolean>(false);

  const loadSubmissions = async (assessmentId: number) => {
    try {
      const res = await api.getSubmissions(assessmentId);
      setSubmissions(res.items);
    } catch {
      setSubmissions([]);
    }
  };

  useEffect(() => {
    const loadAssessments = async () => {
      try {
        const res = await api.getAssessments();
        setAssessments(res.items);
        if (res.items.length > 0) {
          setSelectedAssessmentId(res.items[0].id);
          loadSubmissions(res.items[0].id);
        }
      } catch (err: any) {
        setError(err.message || 'Failed to load assessments.');
      }
    };
    loadAssessments();
  }, []);

  const handleAssessmentChange = (id: number) => {
    setSelectedAssessmentId(id);
    setSession(null);
    setSummary(null);
    setProgressReport(null);
    setShowReport(false);
    loadSubmissions(id);
  };

  const handleCreateSubmission = async () => {
    if (!selectedAssessmentId) return;
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const created = await api.createSubmission(Number(selectedAssessmentId));
      setSuccess(`Submission #${created.id} registered for this assessment.`);
      await loadSubmissions(Number(selectedAssessmentId));
    } catch (err: any) {
      setError(err.message || 'Failed to create submission.');
    } finally {
      setLoading(false);
    }
  };

  const handleStartOrResume = async () => {
    if (!selectedAssessmentId) return;
    setLoading(true);
    setError(null);
    setSuccess(null);
    setSummary(null);

    try {
      // First check if student already has a submission for this assessment
      const subsRes = await api.getSubmissions(Number(selectedAssessmentId));
      let subId: number;

      if (subsRes.items.length > 0) {
        subId = subsRes.items[0].id;
      } else {
        // Create submission
        const createdSub = await api.createSubmission(Number(selectedAssessmentId));
        subId = createdSub.id;
        await loadSubmissions(Number(selectedAssessmentId));
      }

      // Start or resume practice session for this submission
      const sessionRes = await api.startPracticeSession(subId);
      setSession(sessionRes);
      setSuccess('Practice session loaded.');
    } catch (err: any) {
      setError(
        err.message ||
          'No approved practice items found for this assessment yet. Ask your instructor to review and approve practice items.'
      );
      setSession(null);
    } finally {
      setLoading(false);
    }
  };

  const handleAnswerChange = (itemId: number, value: string) => {
    setAnswers((prev) => ({ ...prev, [itemId]: value }));
  };

  const handleSubmitResponse = async (item: StudentPracticeItemRead) => {
    if (!session) return;
    const studentAnswer = answers[item.id];
    if (!studentAnswer || !studentAnswer.trim()) {
      setError('Please provide an answer before submitting.');
      return;
    }

    setSubmittingItemId(item.id);
    setError(null);
    setSuccess(null);

    try {
      await api.submitPracticeResponse(session.id, item.id, studentAnswer.trim());
      // Refresh session to get updated response and score
      const updated = await api.getPracticeSession(session.id);
      setSession(updated);
      setSuccess('Answer submitted and scored.');
      if (showReport && session.submission_id) {
        handleLoadProgressReport(session.submission_id);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to submit response.');
    } finally {
      setSubmittingItemId(null);
    }
  };

  const handleLoadSummary = async () => {
    if (!session) return;
    try {
      const sum = await api.getPracticeSessionSummary(session.id);
      setSummary(sum);
    } catch (err: any) {
      setError(err.message || 'Failed to retrieve session summary.');
    }
  };

  const handleLoadProgressReport = async (submissionIdOverride?: number) => {
    let subId = submissionIdOverride;
    if (!subId && session) {
      subId = session.submission_id;
    }
    if (!subId && submissions.length > 0) {
      subId = submissions[0].id;
    }
    if (!subId) {
      setError('Please start or select a submission first to view your topic progress report.');
      return;
    }

    setLoadingReport(true);
    setError(null);
    try {
      const rep = await api.getStudentProgressReport(subId);
      setProgressReport(rep);
      setShowReport(true);
    } catch (err: any) {
      setError(err.message || 'Failed to load student progress report.');
    } finally {
      setLoadingReport(false);
    }
  };

  const handleCompleteSession = async () => {
    if (!session) return;
    try {
      const completed = await api.completePracticeSession(session.id);
      setSession(completed);
      setSuccess('Practice session marked as completed.');
      handleLoadSummary();
      if (session.submission_id) {
        handleLoadProgressReport(session.submission_id);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to complete session.');
    }
  };

  return (
    <div>
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Student Practice & Formative Feedback</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          Engage with targeted practice questions designed to clarify and reinforce key concepts.
        </p>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      {/* Assessment Selector & Start Button */}
      <div className="card" style={{ padding: '16px 20px', marginBottom: '20px', display: 'flex', gap: '20px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: '240px' }}>
          <label className="form-label" style={{ marginBottom: '6px' }}>Select Assessment</label>
          <select
            className="form-select"
            value={selectedAssessmentId}
            onChange={(e) => handleAssessmentChange(Number(e.target.value))}
          >
            {assessments.map((a) => (
              <option key={a.id} value={a.id}>
                {a.title}
              </option>
            ))}
          </select>
          {submissions.length > 0 && (
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
              Your Submissions for this assessment: {submissions.map(s => `#${s.id} (${s.status})`).join(', ')}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          {submissions.length === 0 && (
            <button
              className="btn btn-secondary"
              onClick={handleCreateSubmission}
              disabled={loading || !selectedAssessmentId}
            >
              Register Submission
            </button>
          )}
          <button
            className="btn btn-primary"
            onClick={handleStartOrResume}
            disabled={loading || !selectedAssessmentId}
          >
            {loading ? <span className="spinner" /> : 'Start / Resume Practice'}
          </button>
          {submissions.length > 0 && (
            <button
              className="btn btn-secondary"
              onClick={() => (showReport ? setShowReport(false) : handleLoadProgressReport())}
              disabled={loadingReport}
              title="Inspect your verified learning progress and outcome tracking across concepts"
            >
              {loadingReport ? (
                <span className="spinner" />
              ) : showReport ? (
                'Hide Topic Progress'
              ) : (
                '📊 Topic Progress & Verification'
              )}
            </button>
          )}
        </div>
      </div>

      {/* Student Progress & Learning Loop Report */}
      {showReport && progressReport && (
        <div className="card" style={{ border: '2px solid var(--primary)', background: 'var(--bg-secondary)', marginBottom: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px' }}>
            <div>
              <h3 className="card-title" style={{ fontSize: '1.2rem', margin: 0 }}>
                🎯 Concept Mastery &amp; Follow-up Verification
              </h3>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
                Tracking: Prior Diagnostic Gap → Follow-up Practice Evidence → Verified Mastery
              </div>
            </div>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setShowReport(false)}
            >
              ✕ Close Report
            </button>
          </div>

          {/* Progress Summary Cards */}
          <div className="grid-4" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', marginBottom: '16px' }}>
            <div className="card" style={{ padding: '12px 14px', background: 'var(--bg-primary)' }}>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Concepts Tracked</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700 }}>{progressReport.total_concepts_tracked}</div>
            </div>
            <div className="card" style={{ padding: '12px 14px', background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
              <div style={{ fontSize: '0.78rem', color: 'var(--success)' }}>Demonstrated Improvement</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--success)' }}>{progressReport.improved_count}</div>
            </div>
            <div className="card" style={{ padding: '12px 14px', background: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.3)' }}>
              <div style={{ fontSize: '0.78rem', color: 'var(--warning)' }}>Tentative / Uncertain</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--warning)' }}>{progressReport.uncertain_count}</div>
            </div>
            <div className="card" style={{ padding: '12px 14px', background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
              <div style={{ fontSize: '0.78rem', color: 'var(--danger)' }}>Persisting Gaps</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--danger)' }}>{progressReport.persisting_gap_count}</div>
            </div>
          </div>

          {/* Next Step Recommendation */}
          <div className="alert alert-info" style={{ marginBottom: '16px', fontSize: '0.9rem' }}>
            <strong>Recommended Next Step:</strong> {progressReport.overall_next_step}
          </div>

          {/* Concept-by-Concept Evidence & Outcome Breakdown */}
          {progressReport.concepts.length === 0 ? (
            <div className="empty-state" style={{ padding: '20px', textAlign: 'center' }}>
              No concept gaps tracked for this submission yet. Complete practice questions to build verified evidence.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginBottom: '16px' }}>
              {progressReport.concepts.map((concept, cIdx) => {
                const statusBadgeClass =
                  concept.outcome_status === 'improved'
                    ? 'badge-success'
                    : concept.outcome_status === 'uncertain'
                    ? 'badge-warning'
                    : concept.outcome_status === 'persisting_gap'
                    ? 'badge-danger'
                    : 'badge-neutral';

                return (
                  <div
                    key={cIdx}
                    className="card"
                    style={{
                      padding: '16px',
                      background: 'var(--bg-primary)',
                      border: '1px solid var(--border-color)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontWeight: 600, fontSize: '1rem' }}>{concept.concept_name}</span>
                        {concept.topic_name && <span className="badge badge-neutral">{concept.topic_name}</span>}
                      </div>
                      <span className={`badge ${statusBadgeClass}`}>
                        {concept.status_label}
                      </span>
                    </div>

                    {/* Baseline vs Followup Grid */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '12px', marginBottom: '12px' }}>
                      {/* Baseline */}
                      <div style={{ background: 'var(--bg-secondary)', padding: '12px', borderRadius: 'var(--radius-sm)' }}>
                        <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#fca5a5', marginBottom: '4px' }}>
                          Original Diagnostic Gap
                        </div>
                        <div style={{ fontSize: '0.85rem' }}>{concept.baseline_diagnostic_gap}</div>
                        {concept.baseline_evidence_excerpt && (
                          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '6px', fontStyle: 'italic' }}>
                            Your Exam Answer: &ldquo;{concept.baseline_evidence_excerpt}&rdquo;
                          </div>
                        )}
                      </div>

                      {/* Follow-up Evidence */}
                      <div style={{ background: 'var(--bg-secondary)', padding: '12px', borderRadius: 'var(--radius-sm)' }}>
                        <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#86efac', marginBottom: '4px' }}>
                          Follow-up Practice Evidence
                        </div>
                        <div style={{ fontSize: '0.85rem' }}>
                          {concept.correct_count} of {concept.evidence_count} practice items correct ({concept.accuracy_percentage.toFixed(0)}%)
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
                          <strong>Uncertainty:</strong> {concept.uncertainty_level} &mdash; {concept.uncertainty_rationale}
                        </div>
                      </div>
                    </div>

                    {/* Remaining Gaps & Guidance */}
                    {concept.remaining_gaps && (
                      <div style={{ fontSize: '0.85rem', color: 'var(--warning)', marginBottom: '8px' }}>
                        <strong>Remaining Gap:</strong> {concept.remaining_gaps}
                      </div>
                    )}

                    <div style={{ fontSize: '0.85rem', color: 'var(--info)' }}>
                      <strong>Recommended Next Step:</strong> {concept.recommended_next_step}
                    </div>

                    {/* Follow-up student responses list */}
                    {concept.followup_responses && concept.followup_responses.length > 0 && (
                      <div style={{ marginTop: '12px', borderTop: '1px solid var(--border-color)', paddingTop: '10px' }}>
                        <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>
                          Your Practice Responses ({concept.followup_responses.length}):
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                          {concept.followup_responses.map((resp, rIdx) => (
                            <div
                              key={rIdx}
                              style={{
                                fontSize: '0.82rem',
                                background: 'var(--bg-tertiary)',
                                padding: '6px 10px',
                                borderRadius: '4px',
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                              }}
                            >
                              <div>
                                <span style={{ fontWeight: 500 }}>Response #{rIdx + 1}: </span>
                                <span>&ldquo;{resp.student_answer}&rdquo;</span>
                                {resp.feedback && (
                                  <span style={{ color: 'var(--text-secondary)', marginLeft: '8px' }}>
                                    &mdash; {resp.feedback}
                                  </span>
                                )}
                              </div>
                              <span className={`badge badge-${resp.is_correct ? 'success' : 'danger'}`} style={{ fontSize: '0.72rem' }}>
                                {resp.is_correct ? 'Correct' : 'Needs Practice'}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Disclaimer */}
          <div className="alert alert-info" style={{ fontSize: '0.82rem', marginBottom: 0 }}>
            <strong>Pedagogical Disclaimer:</strong> {progressReport.pedagogical_disclaimer}
          </div>
        </div>
      )}

      {session && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Session Header Status */}
          <div className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-tertiary)' }}>
            <div>
              <span style={{ fontWeight: 600 }}>Practice Session #{session.id}</span>
              <span className={`badge badge-${session.status === 'completed' ? 'success' : 'info'}`} style={{ marginLeft: '12px' }}>
                {session.status}
              </span>
              <span style={{ marginLeft: '16px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Items: {session.responses.length} / {session.items.length} Answered
              </span>
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => handleLoadProgressReport(session.submission_id)}
                disabled={loadingReport}
              >
                {loadingReport ? <span className="spinner" /> : '📊 Topic Progress'}
              </button>
              <button className="btn btn-secondary btn-sm" onClick={handleLoadSummary}>
                View Summary
              </button>
              {session.status === 'active' && (
                <button className="btn btn-success btn-sm" onClick={handleCompleteSession}>
                  Finish Session
                </button>
              )}
            </div>
          </div>

          {/* Formative Summary Modal/Section */}
          {summary && (
            <div className="card" style={{ borderColor: 'var(--info)' }}>
              <div className="card-header">
                <h3 className="card-title">Practice Session Performance Summary</h3>
                <span className="badge badge-info">{summary.accuracy_percentage.toFixed(0)}% Accuracy</span>
              </div>

              <div className="grid-3" style={{ marginBottom: '16px' }}>
                <div style={{ background: 'var(--bg-primary)', padding: '12px', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Total Questions</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 700 }}>{summary.total_items}</div>
                </div>
                <div style={{ background: 'var(--bg-primary)', padding: '12px', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Completed</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 700 }}>{summary.completed_items}</div>
                </div>
                <div style={{ background: 'var(--bg-primary)', padding: '12px', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Correct Answers</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--success)' }}>
                    {summary.correct_count ?? summary.correct_items ?? 0}
                  </div>
                </div>
              </div>

              {summary.concepts_practiced && summary.concepts_practiced.length > 0 && (
                <div style={{ marginBottom: '16px' }}>
                  <div style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '8px' }}>Concept Evidence Breakdown:</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {summary.concepts_practiced.map((cb, idx) => (
                      <div
                        key={idx}
                        style={{
                          background: 'var(--bg-primary)',
                          padding: '10px 14px',
                          borderRadius: 'var(--radius-sm)',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          fontSize: '0.88rem',
                        }}
                      >
                        <span>{cb.concept_name}</span>
                        <span>
                          {cb.correct_count}/{cb.items_count} Correct ({cb.evidence_summary})
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="alert alert-info" style={{ fontSize: '0.82rem', marginBottom: 0 }}>
                <strong>Pedagogical Disclaimer:</strong> {summary.pedagogical_disclaimer}
              </div>
            </div>
          )}

          {/* Practice Questions List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {session.items.map((item, idx) => {
              const existingResponse = session.responses.find((r) => r.remediation_item_id === item.id);
              const isAnswered = !!existingResponse;
              const isSubmitting = submittingItemId === item.id;

              return (
                <div
                  key={item.id}
                  className="card"
                  style={{
                    borderColor: isAnswered
                      ? existingResponse.is_correct
                        ? 'var(--success)'
                        : 'var(--warning)'
                      : 'var(--border-color)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <span style={{ fontWeight: 600, fontSize: '1.05rem' }}>
                      Question {idx + 1}
                    </span>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <span className="badge badge-neutral">{item.question_type}</span>
                      {isAnswered && (
                        <span className={`badge badge-${existingResponse.is_correct ? 'success' : 'warning'}`}>
                          {existingResponse.is_correct ? 'Correct' : 'Needs Practice'}
                        </span>
                      )}
                    </div>
                  </div>

                  <div style={{ fontSize: '1rem', marginBottom: '16px', lineHeight: 1.6 }}>
                    {item.question_text || item.prompt}
                  </div>

                  {/* Render Answer Input */}
                  {item.question_type === 'mcq' && item.options ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
                      {item.options.map((opt, oIdx) => (
                        <label
                          key={oIdx}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            background: 'var(--bg-primary)',
                            padding: '10px 14px',
                            borderRadius: 'var(--radius-sm)',
                            cursor: isAnswered ? 'default' : 'pointer',
                            border: `1px solid ${answers[item.id] === opt.charAt(0) ? 'var(--primary)' : 'var(--border-color)'}`,
                          }}
                        >
                          <input
                            type="radio"
                            name={`mcq_${item.id}`}
                            value={opt.charAt(0)}
                            checked={
                              isAnswered
                                ? existingResponse.student_answer.toUpperCase().startsWith(opt.charAt(0).toUpperCase())
                                : answers[item.id] === opt.charAt(0)
                            }
                            onChange={(e) => handleAnswerChange(item.id, e.target.value)}
                            disabled={isAnswered || session.status !== 'active'}
                          />
                          <span>{opt}</span>
                        </label>
                      ))}
                    </div>
                  ) : (
                    <div className="form-group" style={{ marginBottom: '16px' }}>
                      <label className="form-label">Your Response</label>
                      <textarea
                        className="form-textarea"
                        placeholder="Type your explanation or answer..."
                        value={isAnswered ? existingResponse.student_answer : answers[item.id] || ''}
                        onChange={(e) => handleAnswerChange(item.id, e.target.value)}
                        disabled={isAnswered || session.status !== 'active'}
                      />
                    </div>
                  )}

                  {/* Formative Feedback if already answered */}
                  {isAnswered ? (
                    <div
                      style={{
                        background: existingResponse.is_correct ? 'var(--success-bg)' : 'var(--warning-bg)',
                        padding: '12px 16px',
                        borderRadius: 'var(--radius-sm)',
                        border: `1px solid ${existingResponse.is_correct ? 'var(--success)' : 'var(--warning)'}`,
                        fontSize: '0.9rem',
                      }}
                    >
                      <div style={{ fontWeight: 600, marginBottom: '4px' }}>
                        {existingResponse.is_correct ? 'Great Job!' : 'Formative Feedback:'}
                      </div>
                      <div>{existingResponse.feedback || 'Answer recorded.'}</div>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                      <button
                        className="btn btn-primary"
                        onClick={() => handleSubmitResponse(item)}
                        disabled={isSubmitting || session.status !== 'active'}
                      >
                        {isSubmitting ? <span className="spinner" /> : 'Submit Answer'}
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
