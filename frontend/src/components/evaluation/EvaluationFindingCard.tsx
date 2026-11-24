import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { EvaluationFinding, FindingCorrection, FollowUpQuestion, CorrectionFieldName } from '../../types';
import { CircularProgressRing } from '../common/CircularProgressRing';

export interface EvaluationFindingCardProps {
  finding: EvaluationFinding;
  initialFollowUps?: FollowUpQuestion[];
  initialCorrections?: FindingCorrection[];
  ocrConfidence?: number | null;
  isReviewing?: boolean;
  isGenerating?: boolean;
  notesValue?: string;
  onNotesChange?: (val: string) => void;
  onReview: (
    findingId: number,
    action: 'accepted' | 'rejected' | 'needs_revision',
    reviewNotes?: string,
    acknowledgeUncertainty?: boolean
  ) => void;
  onGenerateRemediation?: (findingId: number) => void;
}

export const getCategoryBadgeClass = (category?: string): string => {
  switch (category) {
    case 'correct_understanding':
      return 'badge-success';
    case 'likely_misconception':
      return 'badge-danger';
    case 'partially_correct_understanding':
    case 'partial_understanding':
    case 'procedural_error':
      return 'badge-warning';
    case 'insufficient_evidence':
      return 'badge-neutral';
    default:
      return 'badge-info';
  }
};

export const EvaluationFindingCard: React.FC<EvaluationFindingCardProps> = ({
  finding,
  initialFollowUps,
  initialCorrections,
  ocrConfidence,
  isReviewing = false,
  isGenerating = false,
  notesValue,
  onNotesChange,
  onReview,
  onGenerateRemediation,
}) => {
  const [acknowledgedUncertainty, setAcknowledgedUncertainty] = useState(false);
  const [internalNotes, setInternalNotes] = useState(finding.review_notes || '');
  const [followUps, setFollowUps] = useState<FollowUpQuestion[]>(initialFollowUps || []);
  const [isProposingFollowUp, setIsProposingFollowUp] = useState(false);
  const [followUpError, setFollowUpError] = useState<string | null>(null);
  const [revealExpectedAnswer, setRevealExpectedAnswer] = useState<{ [id: number]: boolean }>({});
  const [rejectReason, setRejectReason] = useState<{ [id: number]: string }>({});
  const [isRejecting, setIsRejecting] = useState<{ [id: number]: boolean }>({});
  const [showNotesDrawer, setShowNotesDrawer] = useState<boolean>(false);

  // Feature 2: Teacher Corrections State
  const [corrections, setCorrections] = useState<FindingCorrection[]>(initialCorrections || []);
  const [editingField, setEditingField] = useState<CorrectionFieldName | null>(null);
  const [editValue, setEditValue] = useState<string>('');
  const [editReason, setEditReason] = useState<string>('');
  const [correctionError, setCorrectionError] = useState<string | null>(null);
  const [isSavingCorrection, setIsSavingCorrection] = useState<boolean>(false);

  const reviewStatus = finding.review_status || 'pending_review';
  const effectiveNotes = notesValue !== undefined ? notesValue : internalNotes;

  useEffect(() => {
    let active = true;
    api
      .getCorrectionsForFinding(finding.id)
      .then((items) => {
        if (active && items) setCorrections(items);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [finding.id]);

  const getActiveCorrection = (f: CorrectionFieldName): FindingCorrection | undefined => {
    return corrections.find((c) => c.field_name === f && c.status === 'active');
  };

  const isTeacherCorrected = Boolean(
    finding.teacher_corrected || corrections.some((c) => c.status === 'active')
  );

  const handleStartEdit = (fieldName: CorrectionFieldName, currentVal: any) => {
    setEditingField(fieldName);
    setEditValue(currentVal !== undefined && currentVal !== null ? String(currentVal) : '');
    setEditReason('');
    setCorrectionError(null);
  };

  const handleSaveCorrection = async (fieldName: CorrectionFieldName) => {
    if (!editReason.trim()) {
      setCorrectionError('A non-empty correction reason is required.');
      return;
    }
    setIsSavingCorrection(true);
    setCorrectionError(null);
    try {
      let finalVal: any = editValue.trim();
      if (fieldName === 'confidence_score') {
        const num = parseFloat(finalVal);
        if (isNaN(num) || num < 0 || num > 1) {
          throw new Error('Confidence score must be a number between 0.0 and 1.0.');
        }
        finalVal = num;
      }
      const newCorr = await api.applyCorrection(finding.id, fieldName, finalVal, editReason.trim());
      setCorrections((prev) => [newCorr, ...prev.filter((c) => c.id !== newCorr.id)]);
      setEditingField(null);
    } catch (err: any) {
      setCorrectionError(err?.message || 'Failed to save correction.');
    } finally {
      setIsSavingCorrection(false);
    }
  };

  const handleRevertCorrection = async (corrId: number) => {
    try {
      const reverted = await api.revertCorrection(finding.id, corrId);
      setCorrections((prev) => prev.map((c) => (c.id === corrId ? reverted : c)));
    } catch (err: any) {
      setCorrectionError(err?.message || 'Failed to revert correction.');
    }
  };

  useEffect(() => {
    let active = true;
    if (reviewStatus === 'accepted') {
      api
        .getFollowUpsForFinding(finding.id)
        .then((items) => {
          if (active && items) setFollowUps(items);
        })
        .catch(() => {});
    }
    return () => {
      active = false;
    };
  }, [finding.id, reviewStatus]);

  const hasMisconception = Boolean(
    (finding.misconceptions && finding.misconceptions.length > 0) ||
      finding.misconception_hypothesis
  );

  const isLowConfidenceUnacknowledged = Boolean(
    finding.requires_teacher_review && !finding.acknowledged_uncertainty
  );

  const canGenerateFollowUp =
    hasMisconception &&
    !isLowConfidenceUnacknowledged &&
    reviewStatus === 'accepted' &&
    !isProposingFollowUp;

  const handleProposeFollowUp = async () => {
    setIsProposingFollowUp(true);
    setFollowUpError(null);
    try {
      const created = await api.proposeFollowUp(finding.id);
      setFollowUps((prev) => [created, ...prev.filter((f) => f.id !== created.id)]);
    } catch (err: any) {
      setFollowUpError(err?.message || 'Failed to generate follow-up question.');
    } finally {
      setIsProposingFollowUp(false);
    }
  };

  const handleApproveFollowUp = async (id: number) => {
    try {
      const updated = await api.approveFollowUp(id);
      setFollowUps((prev) => prev.map((f) => (f.id === id ? updated : f)));
    } catch (err: any) {
      setFollowUpError(err?.message || 'Failed to approve follow-up question.');
    }
  };

  const handleRejectFollowUp = async (id: number) => {
    const reason = rejectReason[id]?.trim() || 'Question rejected by teacher review';
    try {
      const updated = await api.rejectFollowUp(id, reason);
      setFollowUps((prev) => prev.map((f) => (f.id === id ? updated : f)));
      setIsRejecting((prev) => ({ ...prev, [id]: false }));
    } catch (err: any) {
      setFollowUpError(err?.message || 'Failed to reject follow-up question.');
    }
  };

  const handleNotesUpdate = (val: string) => {
    if (onNotesChange) {
      onNotesChange(val);
    } else {
      setInternalNotes(val);
    }
  };

  const statusBadgeClass =
    reviewStatus === 'accepted'
      ? 'badge-success'
      : reviewStatus === 'rejected'
      ? 'badge-danger'
      : reviewStatus === 'needs_revision'
      ? 'badge-warning'
      : 'badge-neutral';

  const diagScore =
    finding.confidence_details?.score !== undefined
      ? finding.confidence_details.score
      : finding.confidence;

  const diagLevel =
    finding.confidence_details?.level ||
    (diagScore < 0.7 ? 'low' : diagScore < 0.85 ? 'medium' : 'high');

  const levelBadgeClass =
    diagLevel === 'high'
      ? 'badge-success'
      : diagLevel === 'medium'
      ? 'badge-warning'
      : 'badge-danger';

  const requiresReview = Boolean(
    finding.requires_teacher_review || diagLevel === 'low'
  );

  const canAccept = !isReviewing && reviewStatus !== 'accepted' && (!requiresReview || acknowledgedUncertainty);

  const renderInlineEditor = (fieldName: CorrectionFieldName) => (
    <div
      data-testid={`correction-editor-${fieldName}`}
      style={{
        marginTop: '6px',
        padding: '8px',
        background: 'var(--bg-secondary, #f8fafc)',
        borderRadius: '6px',
        border: '1px solid var(--border-color, #cbd5e1)',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <input
          type={fieldName === 'confidence_score' ? 'number' : 'text'}
          step={fieldName === 'confidence_score' ? '0.01' : undefined}
          min={fieldName === 'confidence_score' ? '0' : undefined}
          max={fieldName === 'confidence_score' ? '1' : undefined}
          className="form-input form-input-sm"
          data-testid={`correction-value-input-${fieldName}`}
          placeholder={`New ${fieldName.replace(/_/g, ' ')} value...`}
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          disabled={isSavingCorrection}
          style={{ fontSize: '0.82rem', padding: '4px 8px' }}
        />
        <input
          type="text"
          className="form-input form-input-sm"
          data-testid={`correction-reason-input-${fieldName}`}
          placeholder="Correction reason (required)..."
          value={editReason}
          onChange={(e) => setEditReason(e.target.value)}
          disabled={isSavingCorrection}
          style={{ fontSize: '0.82rem', padding: '4px 8px' }}
        />
        {correctionError && (
          <div style={{ color: '#ef4444', fontSize: '0.75rem' }}>{correctionError}</div>
        )}
        <div style={{ display: 'flex', gap: '6px' }}>
          <button
            type="button"
            className="btn btn-primary btn-xs"
            data-testid={`save-correction-btn-${fieldName}`}
            onClick={() => handleSaveCorrection(fieldName)}
            disabled={isSavingCorrection}
          >
            {isSavingCorrection ? 'Saving...' : 'Save Correction'}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-xs"
            onClick={() => setEditingField(null)}
            disabled={isSavingCorrection}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );

  const renderCorrectionDetails = (fieldName: CorrectionFieldName) => {
    const active = getActiveCorrection(fieldName);
    if (!active) return null;
    return (
      <div
        data-testid={`correction-details-${fieldName}`}
        style={{
          marginTop: '4px',
          padding: '4px 8px',
          background: 'rgba(59, 130, 246, 0.08)',
          borderRadius: '4px',
          borderLeft: '3px solid #3b82f6',
          fontSize: '0.78rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '6px',
        }}
      >
        <div>
          <span className="badge badge-info" style={{ fontSize: '0.68rem', marginRight: '6px' }}>
            Teacher Corrected
          </span>
          <span style={{ color: 'var(--text-secondary)' }}>
            AI Original: <del>{String(active.original_value ?? 'N/A')}</del>
          </span>
          <span style={{ marginLeft: '8px', fontWeight: 600, color: '#1d4ed8' }}>
            Active: {String(active.corrected_value)}
          </span>
          <span style={{ marginLeft: '8px', fontStyle: 'italic', color: 'var(--text-secondary)' }}>
            (Reason: {active.correction_reason})
          </span>
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-xs"
          data-testid={`revert-correction-btn-${fieldName}`}
          onClick={() => handleRevertCorrection(active.id)}
          style={{ fontSize: '0.72rem', color: '#ef4444', padding: '1px 6px' }}
        >
          Revert to AI
        </button>
      </div>
    );
  };

  const activeHyp = getActiveCorrection('misconception_hypothesis');
  const activeConcept = getActiveCorrection('linked_concept');
  const activeEvidence = getActiveCorrection('evidence_excerpt');

  return (
    <div className="finding-card finding-card-modern glass-card" data-testid={`finding-card-${finding.id}`}>
      {/* Header Bar */}
      <div className="finding-card-header">
        <div className="finding-concept" style={{ flexWrap: 'wrap', gap: '6px' }}>
          <span className="concept-title">{finding.concept_name || 'Concept Finding'}</span>
          {isTeacherCorrected && (
            <span
              data-testid="teacher-corrected-badge"
              className="badge"
              style={{ fontWeight: 600, background: '#2563eb', color: '#ffffff', fontSize: '0.75rem' }}
            >
              Teacher Corrected
            </span>
          )}
          {finding.verdict && (
            <span
              className={`badge ${
                finding.verdict === 'correct'
                  ? 'badge-success'
                  : finding.verdict === 'partially_correct'
                  ? 'badge-warning'
                  : finding.verdict === 'incorrect'
                  ? 'badge-danger'
                  : 'badge-warning'
              }`}
              style={{ fontWeight: 600 }}
            >
              {finding.verdict === 'correct'
                ? '✓ Correct'
                : finding.verdict === 'partially_correct'
                ? '⚠ Partially Correct'
                : finding.verdict === 'incorrect'
                ? '✗ Incorrect'
                : '🔍 Review Required'}
            </span>
          )}
          {finding.marks_awarded !== undefined && finding.marks_awarded !== null && (
            <span className="badge badge-neutral" style={{ fontWeight: 600 }}>
              {finding.marks_awarded} / {finding.max_marks || 1} Marks
            </span>
          )}
          {finding.error_amount && (
            <span className="badge badge-danger">
              Error: {finding.error_amount}
            </span>
          )}
          {finding.error_type && (
            <span className="badge badge-neutral" style={{ fontSize: '0.75rem' }}>
              {finding.error_type.replace(/_/g, ' ')}
            </span>
          )}
          <span className={`badge ${getCategoryBadgeClass(finding.category)}`}>
            {finding.category ? finding.category.replace(/_/g, ' ') : 'General'}
          </span>
          <span className={`badge ${statusBadgeClass}`}>
            {reviewStatus.replace('_', ' ').toUpperCase()}
          </span>
        </div>
      </div>

      {/* Dual Confidence Panel: OCR extraction confidence vs Diagnostic evaluation confidence */}
      <div
        className="confidence-panel"
        style={{
          marginTop: '8px',
          padding: '8px 12px',
          background: 'var(--bg-secondary, #f8fafc)',
          borderRadius: '6px',
          border: '1px solid var(--border-color, #e2e8f0)',
          display: 'flex',
          flexWrap: 'wrap',
          gap: '12px',
          alignItems: 'center',
          fontSize: '0.84rem',
        }}
      >
        {ocrConfidence !== undefined && ocrConfidence !== null && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CircularProgressRing percentage={Math.round(ocrConfidence * 100)} size={34} strokeWidth={3} />
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ color: 'var(--text-secondary)', fontSize: '0.74rem' }}>OCR Confidence:</span>
              <span className="badge badge-neutral" style={{ fontWeight: 600, width: 'fit-content' }}>
                {Math.round(ocrConfidence * 100)}%
              </span>
            </div>
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <CircularProgressRing percentage={Math.round(diagScore * 100)} size={34} strokeWidth={3} />
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.74rem' }}>Diagnostic Confidence:</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span className="badge badge-neutral" style={{ fontWeight: 600 }}>
                {Math.round(diagScore * 100)}%
              </span>
              <span className={`badge ${levelBadgeClass}`} style={{ textTransform: 'uppercase', fontSize: '0.72rem' }}>
                {diagLevel}
              </span>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-xs"
            data-testid="edit-btn-confidence_score"
            onClick={() => handleStartEdit('confidence_score', diagScore)}
            style={{ fontSize: '0.75rem', padding: '1px 4px', color: '#0284c7' }}
            title="Edit confidence score"
          >
            ✎
          </button>
        </div>

        {finding.confidence_details?.uncertainty_reasons &&
          finding.confidence_details.uncertainty_reasons.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap' }}>
              <span style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>Uncertainty:</span>
              {finding.confidence_details.uncertainty_reasons.map((reason, idx) => (
                <span
                  key={idx}
                  className="badge badge-warning"
                  style={{ fontSize: '0.72rem', padding: '2px 6px' }}
                >
                  {reason.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          )}
      </div>

      {renderCorrectionDetails('confidence_score')}
      {editingField === 'confidence_score' && renderInlineEditor('confidence_score')}

      {/* Clinical Report Body: Split 2-Column Grid */}
      <div className="clinical-split-body">
        {/* Left Column: Extracted Student Work & Model Solution */}
        <div className="clinical-left-pane">
          <div className="finding-evidence">
            <span className="evidence-label">Extracted Student Work &amp; Handwriting OCR</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontStyle: 'italic', color: '#1e293b' }}>
              <blockquote>&ldquo;{activeEvidence ? activeEvidence.corrected_value : (finding.evidence_excerpt || 'Direct student work extracted from script')} &rdquo;</blockquote>
              <button
                type="button"
                className="btn btn-ghost btn-xs"
                data-testid="edit-btn-evidence_excerpt"
                onClick={() => handleStartEdit('evidence_excerpt', finding.evidence_excerpt)}
                style={{ fontSize: '0.75rem', padding: '1px 4px', color: '#0284c7' }}
                title="Edit student evidence excerpt"
              >
                ✎
              </button>
            </div>
            {renderCorrectionDetails('evidence_excerpt')}
            {editingField === 'evidence_excerpt' && renderInlineEditor('evidence_excerpt')}
          </div>

          {finding.correct_answer && (
            <div
              style={{
                padding: '10px 14px',
                background: '#ecfdf5',
                borderRadius: '6px',
                borderLeft: '4px solid #10b981',
                fontSize: '0.86rem',
              }}
            >
              <strong style={{ color: '#065f46' }}>Authoritative Solution: </strong>
              <code style={{ background: 'transparent', color: '#065f46', fontWeight: 600 }}>{finding.correct_answer}</code>
            </div>
          )}

          {finding.marks_reason && (
            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              <strong>Scoring Note:</strong> {finding.marks_reason}
            </div>
          )}
        </div>

        {/* Right Column: AI Diagnostic Analysis & Remediation Focus */}
        <div className="clinical-right-pane">
          {finding.step_by_step_explanation && (
            <div>
              <span className="rationale-label" style={{ color: '#0284c7' }}>Clinical / Pedagogical Analysis</span>
              <p style={{ margin: '4px 0 0 0', fontSize: '0.88rem', color: '#334155', lineHeight: 1.55 }}>
                {finding.step_by_step_explanation}
              </p>
            </div>
          )}

          {finding.rationale && !finding.step_by_step_explanation && (
            <div className="finding-rationale">
              <span className="rationale-label">Pedagogical Rationale</span>
              <p style={{ margin: '4px 0 0 0', fontSize: '0.88rem', color: '#334155', lineHeight: 1.55 }}>
                {finding.rationale}
              </p>
            </div>
          )}

          {finding.remediation_concept && (
            <div
              style={{
                padding: '8px 12px',
                background: '#f0f9ff',
                borderRadius: '6px',
                borderLeft: '3px solid #0284c7',
                fontSize: '0.84rem',
              }}
            >
              <strong style={{ color: '#0369a1' }}>Remediation Focus: </strong>
              <span style={{ color: '#0f172a' }}>{finding.remediation_concept}</span>
            </div>
          )}
        </div>
      </div>

      {/* Structured Misconceptions List (Highlighted Clinical Alert) */}
      {finding.misconceptions && finding.misconceptions.length > 0 ? (
        <div style={{ marginTop: '8px' }}>
          <div style={{ fontSize: '0.86rem', fontWeight: 700, color: '#991b1b', marginBottom: '8px' }}>
            Evidence-Grounded Misconception Hypotheses ({finding.misconceptions.length}):
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {finding.misconceptions.map((misc, idx) => (
              <div
                key={idx}
                style={{
                  padding: '12px 14px',
                  background: '#fef2f2',
                  borderRadius: '6px',
                  border: '1px solid #fecaca',
                  borderLeft: '4px solid #ef4444',
                  fontSize: '0.86rem',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '4px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <strong style={{ color: '#991b1b' }}>
                      {activeHyp ? activeHyp.corrected_value : misc.hypothesis}
                    </strong>
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs"
                      data-testid="edit-btn-misconception_hypothesis"
                      onClick={() => handleStartEdit('misconception_hypothesis', misc.hypothesis)}
                      style={{ fontSize: '0.75rem', padding: '1px 4px', color: '#0284c7' }}
                      title="Edit misconception hypothesis"
                    >
                      ✎
                    </button>
                  </div>
                  {misc.severity && (
                    <span
                      className={`badge ${
                        misc.severity === 'high'
                          ? 'badge-danger'
                          : misc.severity === 'medium'
                          ? 'badge-warning'
                          : 'badge-neutral'
                      }`}
                      style={{ fontSize: '0.7rem' }}
                    >
                      {misc.severity} severity
                    </span>
                  )}
                </div>
                {renderCorrectionDetails('misconception_hypothesis')}
                {editingField === 'misconception_hypothesis' && renderInlineEditor('misconception_hypothesis')}

                {(misc.evidence_excerpt || activeEvidence) && (
                  <div style={{ marginTop: '6px', fontStyle: 'italic', color: '#1e293b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span>&ldquo;{activeEvidence ? activeEvidence.corrected_value : misc.evidence_excerpt}&rdquo;</span>
                  </div>
                )}

                {(misc.linked_concept || activeConcept) && (
                  <div style={{ marginTop: '4px', fontSize: '0.8rem', color: '#475569', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span>Linked Concept: <strong style={{ color: '#0f172a' }}>{activeConcept ? activeConcept.corrected_value : misc.linked_concept}</strong></span>
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs"
                      data-testid="edit-btn-linked_concept"
                      onClick={() => handleStartEdit('linked_concept', misc.linked_concept)}
                      style={{ fontSize: '0.75rem', padding: '1px 4px', color: '#0284c7' }}
                      title="Edit linked concept"
                    >
                      ✎
                    </button>
                  </div>
                )}
                {renderCorrectionDetails('linked_concept')}
                {editingField === 'linked_concept' && renderInlineEditor('linked_concept')}
              </div>
            ))}
          </div>
        </div>
      ) : finding.misconception_hypothesis ? (
        <div style={{ marginTop: '8px', padding: '10px 14px', background: '#fef2f2', border: '1px solid #fecaca', borderLeft: '4px solid #ef4444', borderRadius: '6px', fontSize: '0.86rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <strong style={{ color: '#991b1b' }}>Misconception Hypothesis:</strong>
            <em style={{ color: '#0f172a' }}>{activeHyp ? activeHyp.corrected_value : finding.misconception_hypothesis}</em>
            <button
              type="button"
              className="btn btn-ghost btn-xs"
              data-testid="edit-btn-misconception_hypothesis"
              onClick={() => handleStartEdit('misconception_hypothesis', finding.misconception_hypothesis)}
              style={{ fontSize: '0.75rem', padding: '1px 4px', color: '#0284c7' }}
              title="Edit misconception hypothesis"
            >
              ✎
            </button>
          </div>
          {renderCorrectionDetails('misconception_hypothesis')}
          {editingField === 'misconception_hypothesis' && renderInlineEditor('misconception_hypothesis')}
        </div>
      ) : null}

      {/* Remediation & Follow-up question */}
      {(finding.remediation_concept || finding.follow_up_question) && (
        <div
          style={{
            marginTop: '8px',
            padding: '10px 14px',
            background: '#f0f9ff',
            borderRadius: '6px',
            borderLeft: '4px solid #0284c7',
            fontSize: '0.86rem',
          }}
        >
          {finding.remediation_concept && (
            <div>
              <strong style={{ color: '#0369a1' }}>Remediation Focus:</strong> <span style={{ color: '#0f172a' }}>{finding.remediation_concept}</span>
            </div>
          )}
          {finding.follow_up_question && (
            <div style={{ marginTop: '4px' }}>
              <strong style={{ color: '#0369a1' }}>Targeted Follow-up Verification:</strong> <em style={{ color: '#0f172a' }}>&ldquo;{finding.follow_up_question}&rdquo;</em>
            </div>
          )}
        </div>
      )}

      {/* Uncertainty Note */}
      {finding.uncertainty_rationale && (
        <div className="finding-uncertainty" style={{ marginTop: '8px' }}>
          <span className="uncertainty-label">Uncertainty Note:</span>
          <p>{finding.uncertainty_rationale}</p>
        </div>
      )}

      {/* Follow-up Verification Block */}
      <div
        data-testid="follow-up-verification-block"
        style={{
          marginTop: '12px',
          padding: '16px',
          background: '#f8fafc',
          borderRadius: '8px',
          border: '1px solid #e2e8f0',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
          <div>
            <strong style={{ color: '#0369a1', fontSize: '0.92rem' }}>Targeted Follow-up Verification</strong>
            <p style={{ margin: '2px 0 0 0', fontSize: '0.78rem', color: '#64748b' }}>
              Generate and verify a single targeted question to check for suspected misconception resolution.
            </p>
          </div>
          <button
            type="button"
            className="btn btn-primary btn-sm btn-cta-gradient"
            onClick={handleProposeFollowUp}
            disabled={!canGenerateFollowUp}
            data-testid="generate-follow-up-btn"
            title={
              !hasMisconception
                ? 'Requires at least one grounded misconception'
                : isLowConfidenceUnacknowledged
                ? 'Requires explicit acknowledgement of uncertainty before follow-up generation'
                : reviewStatus !== 'accepted'
                ? 'Finding must be accepted by teacher first'
                : 'Generate diagnostic follow-up question'
            }
          >
            {isProposingFollowUp ? <span className="spinner" /> : '⚡ Generate Follow-up Question'}
          </button>
        </div>

        {followUpError && (
          <div
            className="alert alert-danger"
            data-testid="follow-up-error-banner"
            style={{ marginTop: '8px', padding: '8px 12px', fontSize: '0.82rem', borderRadius: '4px' }}
          >
            <strong>Error:</strong> {followUpError}
          </div>
        )}

        {followUps.length > 0 && (
          <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {followUps.map((fq) => {
              const isRevealed = revealExpectedAnswer[fq.id] || false;
              const statusClass =
                fq.status === 'approved'
                  ? 'badge-success'
                  : fq.status === 'rejected'
                  ? 'badge-danger'
                  : 'badge-warning';

              return (
                <div
                  key={fq.id}
                  data-testid={`follow-up-card-${fq.id}`}
                  style={{
                    padding: '12px 14px',
                    background: '#ffffff',
                    borderRadius: '6px',
                    border: '1px solid #e2e8f0',
                    fontSize: '0.86rem',
                    boxShadow: '0 1px 3px rgba(15, 23, 42, 0.04)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                      Concept: <code>{fq.concept}</code>
                    </span>
                    <span
                      data-testid={`follow-up-status-badge-${fq.id}`}
                      className={`badge ${statusClass}`}
                      style={{ textTransform: 'uppercase', fontSize: '0.72rem' }}
                    >
                      {fq.status}
                    </span>
                  </div>

                  <div style={{ marginBottom: '6px', color: 'var(--text-primary)', fontSize: '0.88rem' }}>
                    <strong>Question:</strong> {fq.question_text}
                  </div>

                  {/* Collapsible Expected Answer */}
                  <div style={{ marginBottom: '6px' }}>
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs"
                      onClick={() =>
                        setRevealExpectedAnswer((prev) => ({ ...prev, [fq.id]: !isRevealed }))
                      }
                      style={{ fontSize: '0.75rem', padding: '2px 6px', color: '#6366f1' }}
                    >
                      {isRevealed ? 'Hide Expected Answer ▲' : 'Show Expected Answer ▼'}
                    </button>
                    {isRevealed && (
                      <div
                        data-testid={`follow-up-expected-answer-${fq.id}`}
                        style={{
                          marginTop: '4px',
                          padding: '6px 10px',
                          background: 'rgba(16, 185, 129, 0.08)',
                          borderRadius: '4px',
                          borderLeft: '3px solid #10b981',
                        }}
                      >
                        <strong style={{ color: '#10b981' }}>Expected Model Answer:</strong> {fq.expected_answer}
                      </div>
                    )}
                  </div>

                  {/* Rubric Display */}
                  {fq.rubric?.criteria && fq.rubric.criteria.length > 0 && (
                    <div style={{ marginBottom: '8px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      <strong>Rubric:</strong>
                      <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                        {fq.rubric.criteria.map((c, idx) => (
                          <li key={idx}>
                            {c.text} ({c.marks} mark{c.marks > 1 ? 's' : ''})
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Follow-up Action Buttons */}
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap', marginTop: '6px' }}>
                    {fq.status === 'proposed' && (
                      <>
                        <button
                          type="button"
                          className="btn btn-success btn-xs"
                          data-testid={`approve-follow-up-btn-${fq.id}`}
                          onClick={() => handleApproveFollowUp(fq.id)}
                        >
                          ✓ Approve Follow-up
                        </button>
                        {!isRejecting[fq.id] ? (
                          <button
                            type="button"
                            className="btn btn-danger btn-xs"
                            data-testid={`reject-follow-up-btn-${fq.id}`}
                            onClick={() => setIsRejecting((prev) => ({ ...prev, [fq.id]: true }))}
                          >
                            ✗ Reject
                          </button>
                        ) : (
                          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                            <input
                              type="text"
                              className="form-input form-input-xs"
                              placeholder="Rejection reason..."
                              value={rejectReason[fq.id] || ''}
                              onChange={(e) =>
                                setRejectReason((prev) => ({ ...prev, [fq.id]: e.target.value }))
                              }
                              style={{ fontSize: '0.75rem', padding: '2px 6px' }}
                            />
                            <button
                              type="button"
                              className="btn btn-danger btn-xs"
                              data-testid={`confirm-reject-follow-up-btn-${fq.id}`}
                              onClick={() => handleRejectFollowUp(fq.id)}
                            >
                              Confirm Reject
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost btn-xs"
                              onClick={() => setIsRejecting((prev) => ({ ...prev, [fq.id]: false }))}
                            >
                              Cancel
                            </button>
                          </div>
                        )}
                      </>
                    )}
                    <button
                      type="button"
                      className="btn btn-secondary btn-xs"
                      data-testid={`regenerate-follow-up-btn-${fq.id}`}
                      onClick={handleProposeFollowUp}
                      disabled={isProposingFollowUp}
                    >
                      ↻ Regenerate
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Teacher Review Gate & Actions */}
      <div
        style={{
          marginTop: '12px',
          paddingTop: '12px',
          borderTop: '1px solid var(--border-color)',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
        }}
      >
        {/* Low Confidence Review Gate Warning */}
        {requiresReview && reviewStatus !== 'accepted' && (
          <div
            className="alert alert-warning"
            style={{
              padding: '8px 12px',
              fontSize: '0.84rem',
              borderRadius: '6px',
              border: '1px solid #f59e0b',
              background: 'rgba(245, 158, 11, 0.08)',
              margin: '0',
            }}
          >
            <div style={{ fontWeight: 600, color: '#b45309', display: 'flex', alignItems: 'center', gap: '6px' }}>
              ⚠️ Review Gate: Low Diagnostic Confidence
            </div>
            <p style={{ margin: '4px 0 6px 0', color: 'var(--text-secondary)' }}>
              This finding has low confidence or unverified evidence. Teacher review and explicit acknowledgement of uncertainty are required before acceptance.
            </p>
            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                cursor: 'pointer',
                fontWeight: 500,
                color: 'var(--text-primary)',
              }}
            >
              <input
                type="checkbox"
                checked={acknowledgedUncertainty}
                onChange={(e) => setAcknowledgedUncertainty(e.target.checked)}
                disabled={isReviewing}
              />
              <span>I acknowledge the diagnostic uncertainty and have verified this finding manually.</span>
            </label>
          </div>
        )}

        {/* Slide-out Review Notes Drawer (Collapsible) */}
        {showNotesDrawer && (
          <div
            style={{
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: '8px',
              padding: '10px 14px',
              marginBottom: '10px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                Teacher Review Rationale / Notes:
              </span>
              <button
                type="button"
                className="btn btn-ghost btn-xs"
                onClick={() => setShowNotesDrawer(false)}
                style={{ fontSize: '0.75rem', padding: '1px 6px' }}
              >
                ✕ Close
              </button>
            </div>
            <input
              type="text"
              className="form-input"
              placeholder="Teacher review notes or rationale..."
              style={{ width: '100%', padding: '6px 10px', fontSize: '0.85rem' }}
              value={effectiveNotes}
              onChange={(e) => handleNotesUpdate(e.target.value)}
              disabled={isReviewing}
              autoFocus
            />
          </div>
        )}

        {/* Clean Action Bar */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
          <button
            type="button"
            className="btn btn-ghost btn-xs"
            onClick={() => setShowNotesDrawer(!showNotesDrawer)}
            style={{ fontSize: '0.78rem', color: effectiveNotes ? '#0284c7' : 'var(--text-secondary)' }}
          >
            {effectiveNotes ? '📝 Note Attached' : '+ Add Review Note'}
          </button>

          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-action-accept"
              onClick={() => onReview(finding.id, 'accepted', effectiveNotes || undefined, acknowledgedUncertainty)}
              disabled={!canAccept}
              title={
                requiresReview && !acknowledgedUncertainty
                  ? 'Check uncertainty acknowledgement to enable acceptance'
                  : 'Accept finding'
              }
            >
              {reviewStatus === 'accepted' ? '✓ Accepted' : 'Accept'}
            </button>
            <button
              type="button"
              className="btn btn-action-flag"
              onClick={() => {
                if (!showNotesDrawer && !effectiveNotes) {
                  setShowNotesDrawer(true);
                } else {
                  onReview(finding.id, 'needs_revision', effectiveNotes || undefined);
                }
              }}
              disabled={isReviewing}
            >
              Flag / Needs Revision
            </button>
            <button
              type="button"
              className="btn btn-action-reject"
              onClick={() => {
                if (!showNotesDrawer && !effectiveNotes) {
                  setShowNotesDrawer(true);
                } else {
                  onReview(finding.id, 'rejected', effectiveNotes || undefined);
                }
              }}
              disabled={isReviewing || reviewStatus === 'rejected'}
            >
              {reviewStatus === 'rejected' ? 'Rejected' : 'Reject'}
            </button>
          </div>
        </div>

        {/* Remediation Generation Trigger (Only on Accepted Findings) */}
        {reviewStatus === 'accepted' && onGenerateRemediation && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => onGenerateRemediation(finding.id)}
              disabled={isGenerating}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              {isGenerating ? <span className="spinner" /> : '⚡ Generate Remediation Items'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
