import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { Assessment, EvaluationFinding, PendingReviewItem } from '../../types';
import { EvaluationFindingCard } from '../evaluation/EvaluationFindingCard';

export interface ReviewQueueProps {
  onSelectFinding?: (findingId: number, submissionId: number) => void;
  initialAssessmentId?: number;
}

export const ReviewQueue: React.FC<ReviewQueueProps> = ({
  onSelectFinding,
  initialAssessmentId,
}) => {
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<number | ''>(
    initialAssessmentId ?? ''
  );
  const [sortOrder, setSortOrder] = useState<string>('priority');
  const [queueItems, setQueueItems] = useState<PendingReviewItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<PendingReviewItem | null>(null);
  const [selectedFinding, setSelectedFinding] = useState<EvaluationFinding | null>(null);
  const [findingLoading, setFindingLoading] = useState<boolean>(false);
  const [hoveredReasonFindingId, setHoveredReasonFindingId] = useState<number | null>(null);

  // Load assessments for filter dropdown
  useEffect(() => {
    let mounted = true;
    const loadAssessments = async () => {
      try {
        const res = await api.getAssessments();
        if (mounted) {
          setAssessments(res.items || []);
        }
      } catch (err: any) {
        // Silently tolerate if assessments fail to load
      }
    };
    loadAssessments();
    return () => {
      mounted = false;
    };
  }, []);

  // Fetch pending review queue items
  const fetchQueue = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getPendingReviewQueue({
        assessment_id: selectedAssessmentId !== '' ? Number(selectedAssessmentId) : undefined,
        sort: sortOrder,
        page: 1,
        page_size: 50,
      });
      setQueueItems(res.items || []);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch pending review queue.');
      setQueueItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQueue();
  }, [selectedAssessmentId, sortOrder]);

  // Load full finding details when row is selected for deep link review
  const handleRowClick = async (item: PendingReviewItem) => {
    setSelectedItem(item);
    if (onSelectFinding) {
      onSelectFinding(item.finding_id, item.submission_id);
    }

    setFindingLoading(true);
    try {
      const evalSummary = await api.getSubmissionEvaluations(item.submission_id);
      let found: EvaluationFinding | null = null;
      for (const run of evalSummary.runs || []) {
        for (const f of run.findings || []) {
          if (f.id === item.finding_id) {
            found = f;
            break;
          }
        }
        if (found) break;
      }
      setSelectedFinding(found);
    } catch {
      setSelectedFinding(null);
    } finally {
      setFindingLoading(false);
    }
  };

  const handleReviewAction = async (
    findingId: number,
    action: 'accepted' | 'rejected' | 'needs_revision',
    reviewNotes?: string,
    acknowledgeUncertainty?: boolean
  ) => {
    try {
      await api.reviewFinding(findingId, action as any, reviewNotes, acknowledgeUncertainty);
      // Refresh queue
      await fetchQueue();
      setSelectedItem(null);
      setSelectedFinding(null);
    } catch (err: any) {
      setError(err.message || 'Failed to update finding review status.');
    }
  };

  return (
    <div className="review-queue-container" style={{ padding: '20px' }}>
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0 0 6px 0' }}>
          Confidence-Aware Teacher Review Queue
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.92rem', margin: 0 }}>
          Prioritized attention queue for student answer evaluations requiring teacher confirmation.
        </p>
      </div>

      {/* Filter and Control Bar */}
      <div
        className="card"
        style={{
          padding: '16px 20px',
          marginBottom: '20px',
          display: 'flex',
          gap: '20px',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
          <div>
            <label
              htmlFor="assessment-filter-select"
              style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '4px' }}
            >
              Filter by Assessment:
            </label>
            <select
              id="assessment-filter-select"
              data-testid="assessment-filter-select"
              className="form-select"
              value={selectedAssessmentId}
              onChange={(e) => setSelectedAssessmentId(e.target.value === '' ? '' : Number(e.target.value))}
              style={{ minWidth: '220px' }}
            >
              <option value="">All Assessments</option>
              {assessments.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.title} (ID #{a.id})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              htmlFor="sort-order-select"
              style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '4px' }}
            >
              Sort Order:
            </label>
            <select
              id="sort-order-select"
              data-testid="sort-order-select"
              className="form-select"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value)}
              style={{ minWidth: '180px' }}
            >
              <option value="priority">Priority (Highest First)</option>
              <option value="created_at">Date Created</option>
            </select>
          </div>
        </div>

        <div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={fetchQueue}
            data-testid="refresh-queue-btn"
          >
            ↻ Refresh Queue
          </button>
        </div>
      </div>

      {/* State Feedback: Loading, Error, Empty */}
      {loading && (
        <div
          data-testid="queue-loading-state"
          style={{
            padding: '40px',
            textAlign: 'center',
            color: 'var(--text-secondary)',
            fontSize: '1rem',
          }}
        >
          Loading review queue...
        </div>
      )}

      {error && !loading && (
        <div data-testid="queue-error-state" className="alert alert-danger" style={{ marginBottom: '20px' }}>
          {error}
        </div>
      )}

      {!loading && !error && queueItems.length === 0 && (
        <div
          data-testid="queue-empty-state"
          className="card"
          style={{
            padding: '40px 20px',
            textAlign: 'center',
            color: 'var(--text-secondary)',
          }}
        >
          <div style={{ fontSize: '2rem', marginBottom: '12px' }}>✓</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
            No pending findings require review
          </div>
          <p style={{ margin: 0, fontSize: '0.9rem' }}>
            All findings for this filter are either reviewed, high confidence, or acknowledged.
          </p>
        </div>
      )}

      {/* Queue Table */}
      {!loading && queueItems.length > 0 && (
        <div className="card" style={{ overflowX: 'auto', marginBottom: '24px' }}>
          <table
            data-testid="review-queue-table"
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '0.9rem',
              textAlign: 'left',
            }}
          >
            <thead>
              <tr
                style={{
                  borderBottom: '1px solid var(--border-color)',
                  background: 'rgba(255, 255, 255, 0.02)',
                }}
              >
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>Priority</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>Student</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>Assessment & Question</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>Finding Concept & Reason</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>Confidence</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>Status Flags</th>
                <th style={{ padding: '12px 16px', fontWeight: 600, textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {queueItems.map((item) => {
                const isSelected = selectedItem?.finding_id === item.finding_id;
                const isHovered = hoveredReasonFindingId === item.finding_id;

                return (
                  <tr
                    key={item.finding_id}
                    data-testid={`review-row-${item.finding_id}`}
                    onClick={() => handleRowClick(item)}
                    style={{
                      borderBottom: '1px solid var(--border-color)',
                      cursor: 'pointer',
                      background: isSelected ? 'rgba(59, 130, 246, 0.08)' : 'transparent',
                      transition: 'background 0.15s ease',
                    }}
                  >
                    {/* Priority Score & Tooltip Reasons */}
                    <td style={{ padding: '12px 16px', verticalAlign: 'middle', position: 'relative' }}>
                      <div
                        data-testid={`priority-badge-${item.finding_id}`}
                        title={item.priority_reasons.join('\n')}
                        onMouseEnter={() => setHoveredReasonFindingId(item.finding_id)}
                        onMouseLeave={() => setHoveredReasonFindingId(null)}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                          padding: '4px 10px',
                          borderRadius: '12px',
                          fontWeight: 700,
                          fontSize: '0.85rem',
                          background:
                            item.priority_score >= 80
                              ? 'rgba(239, 68, 68, 0.15)'
                              : item.priority_score >= 40
                              ? 'rgba(245, 158, 11, 0.15)'
                              : 'rgba(59, 130, 246, 0.15)',
                          color:
                            item.priority_score >= 80
                              ? '#ef4444'
                              : item.priority_score >= 40
                              ? '#f59e0b'
                              : '#3b82f6',
                          border: `1px solid ${
                            item.priority_score >= 80
                              ? 'rgba(239, 68, 68, 0.3)'
                              : item.priority_score >= 40
                              ? 'rgba(245, 158, 11, 0.3)'
                              : 'rgba(59, 130, 246, 0.3)'
                          }`,
                        }}
                      >
                        ⚡ {item.priority_score}
                      </div>

                      {/* Tooltip Overlay */}
                      {isHovered && item.priority_reasons.length > 0 && (
                        <div
                          data-testid={`priority-reasons-tooltip-${item.finding_id}`}
                          style={{
                            position: 'absolute',
                            left: '16px',
                            top: '44px',
                            zIndex: 100,
                            background: '#1f2937',
                            border: '1px solid #374151',
                            borderRadius: '6px',
                            padding: '8px 12px',
                            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.5)',
                            fontSize: '0.78rem',
                            color: '#e5e7eb',
                            minWidth: '220px',
                            pointerEvents: 'none',
                          }}
                        >
                          <div style={{ fontWeight: 600, marginBottom: '4px', color: '#93c5fd' }}>
                            Priority Factors:
                          </div>
                          <ul style={{ margin: 0, paddingLeft: '16px' }}>
                            {item.priority_reasons.map((r, i) => (
                              <li key={i}>{r}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </td>

                    {/* Student */}
                    <td style={{ padding: '12px 16px', verticalAlign: 'middle', fontWeight: 600 }}>
                      {item.student_name}
                    </td>

                    {/* Assessment & Question */}
                    <td style={{ padding: '12px 16px', verticalAlign: 'middle' }}>
                      <div style={{ fontWeight: 500 }}>{item.assessment_title || `Assessment #${item.assessment_id}`}</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                        Question {item.question_number ?? item.question_id}
                      </div>
                    </td>

                    {/* Finding Concept & Summary */}
                    <td style={{ padding: '12px 16px', verticalAlign: 'middle', maxWidth: '280px' }}>
                      <div style={{ fontWeight: 600, color: '#fca5a5' }}>
                        {item.concept_name || item.category}
                      </div>
                      <div
                        style={{
                          fontSize: '0.82rem',
                          color: 'var(--text-secondary)',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {item.brief_text || 'No excerpt available.'}
                      </div>
                    </td>

                    {/* Confidence */}
                    <td style={{ padding: '12px 16px', verticalAlign: 'middle' }}>
                      <span
                        className={`badge ${
                          item.confidence < 0.7
                            ? 'badge-danger'
                            : item.confidence < 0.85
                            ? 'badge-warning'
                            : 'badge-success'
                        }`}
                      >
                        {(item.confidence * 100).toFixed(0)}%
                      </span>
                    </td>

                    {/* Status Flags */}
                    <td style={{ padding: '12px 16px', verticalAlign: 'middle' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        {item.requires_teacher_review && (
                          <span
                            className="badge badge-warning"
                            data-testid={`gate-badge-${item.finding_id}`}
                            style={{ fontSize: '0.72rem', alignSelf: 'flex-start' }}
                          >
                            Review Required
                          </span>
                        )}
                        {item.teacher_corrected && (
                          <span
                            className="badge badge-info"
                            data-testid={`corrected-badge-${item.finding_id}`}
                            style={{ fontSize: '0.72rem', alignSelf: 'flex-start' }}
                          >
                            Teacher Corrected
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Action Deep-Link */}
                    <td style={{ padding: '12px 16px', verticalAlign: 'middle', textAlign: 'right' }}>
                      <button
                        type="button"
                        data-testid={`deep-link-${item.finding_id}`}
                        className="btn btn-secondary btn-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRowClick(item);
                        }}
                      >
                        Review Finding →
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Deep Link Finding View / Inline Detail Drawer */}
      {selectedItem && (
        <div
          data-testid="selected-finding-detail-pane"
          className="card"
          style={{
            padding: '20px',
            border: '2px solid rgba(59, 130, 246, 0.4)',
            marginTop: '20px',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '16px',
            }}
          >
            <div>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, margin: '0 0 4px 0' }}>
                Reviewing Finding #{selectedItem.finding_id} ({selectedItem.student_name})
              </h3>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                {selectedItem.assessment_title} • Question {selectedItem.question_number ?? selectedItem.question_id}
              </div>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => {
                setSelectedItem(null);
                setSelectedFinding(null);
              }}
            >
              ✕ Close Detail
            </button>
          </div>

          {findingLoading && <div>Loading finding full context...</div>}

          {!findingLoading && selectedFinding && (
            <EvaluationFindingCard
              finding={selectedFinding}
              onReview={handleReviewAction}
            />
          )}

          {!findingLoading && !selectedFinding && (
            <div>
              <div className="alert alert-warning">
                Could not load full finding card from submission summary. Showing summary:
              </div>
              <p>
                <strong>Concept:</strong> {selectedItem.concept_name}
              </p>
              <p>
                <strong>Brief Text:</strong> {selectedItem.brief_text}
              </p>
              <p>
                <strong>Priority Reasons:</strong>
              </p>
              <ul>
                {selectedItem.priority_reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

