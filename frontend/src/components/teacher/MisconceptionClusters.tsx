import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { Assessment, MisconceptionClusterItem, MisconceptionClusterResponse } from '../../types';

export interface MisconceptionClustersProps {
  initialAssessmentId?: number;
}

export const MisconceptionClusters: React.FC<MisconceptionClustersProps> = ({
  initialAssessmentId,
}) => {
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<number | ''>(
    initialAssessmentId ?? ''
  );
  const [clusterData, setClusterData] = useState<MisconceptionClusterResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Per-cluster intervention generation state
  const [generatingIntervention, setGeneratingIntervention] = useState<{ [clusterId: string]: boolean }>({});
  const [interventionResults, setInterventionResults] = useState<{
    [clusterId: string]: { successCount: number; totalCount: number; message: string };
  }>({});

  // 1. Load assessments
  useEffect(() => {
    let mounted = true;
    const loadAssessments = async () => {
      try {
        const res = await api.getAssessments();
        if (mounted && res.items?.length > 0) {
          setAssessments(res.items);
          if (selectedAssessmentId === '') {
            setSelectedAssessmentId(res.items[0].id);
          }
        }
      } catch (err: any) {
        // tolerate
      }
    };
    loadAssessments();
    return () => {
      mounted = false;
    };
  }, []);

  // 2. Fetch clusters for selected assessment
  const fetchClusters = async (aid: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getMisconceptionClusters(aid);
      setClusterData(res);
    } catch (err: any) {
      setError(err.message || 'Failed to load misconception clusters.');
      setClusterData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedAssessmentId !== '') {
      fetchClusters(Number(selectedAssessmentId));
    } else {
      setClusterData(null);
      setLoading(false);
    }
  }, [selectedAssessmentId]);

  // Note G (REVISED): Create class intervention by looping over each finding in the cluster
  const handleCreateClassIntervention = async (cluster: MisconceptionClusterItem) => {
    const cId = cluster.cluster_id;
    setGeneratingIntervention((prev) => ({ ...prev, [cId]: true }));
    setError(null);

    let successCount = 0;
    const targetFindings = cluster.finding_ids || [];

    for (const fId of targetFindings) {
      try {
        await api.generateRemediationsForFinding(fId);
        successCount += 1;
      } catch (err: any) {
        // Continue generating for remaining findings in the cluster
      }
    }

    setGeneratingIntervention((prev) => ({ ...prev, [cId]: false }));
    setInterventionResults((prev) => ({
      ...prev,
      [cId]: {
        successCount,
        totalCount: targetFindings.length,
        message: `${successCount} interventions generated`,
      },
    }));
  };

  return (
    <div className="misconception-clusters-container" style={{ padding: '20px' }}>
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0 0 6px 0' }}>
          Class-Level Misconception Aggregation
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.92rem', margin: 0 }}>
          Synthesizes accepted findings into actionable group clusters (≥2 students) to drive targeted class interventions.
        </p>
      </div>

      {/* Assessment Selector Bar */}
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
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
          <div>
            <label
              htmlFor="assessment-cluster-select"
              style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '4px' }}
            >
              Select Assessment:
            </label>
            <select
              id="assessment-cluster-select"
              data-testid="assessment-cluster-select"
              className="form-select"
              value={selectedAssessmentId}
              onChange={(e) => setSelectedAssessmentId(e.target.value === '' ? '' : Number(e.target.value))}
              style={{ minWidth: '240px' }}
            >
              <option value="">Choose an assessment...</option>
              {assessments.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.title} (ID #{a.id})
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => selectedAssessmentId !== '' && fetchClusters(Number(selectedAssessmentId))}
            data-testid="refresh-clusters-btn"
          >
            ↻ Refresh Clusters
          </button>
        </div>
      </div>

      {/* State Feedback: Loading, Error, Empty */}
      {loading && (
        <div
          data-testid="clusters-loading-state"
          style={{
            padding: '40px',
            textAlign: 'center',
            color: 'var(--text-secondary)',
            fontSize: '1rem',
          }}
        >
          Analyzing class-level misconception clusters...
        </div>
      )}

      {error && !loading && (
        <div data-testid="clusters-error-state" className="alert alert-danger" style={{ marginBottom: '20px' }}>
          {error}
        </div>
      )}

      {!loading && !error && clusterData && clusterData.clusters.length === 0 && clusterData.isolated.length === 0 && (
        <div
          data-testid="clusters-empty-state"
          className="card"
          style={{
            padding: '40px 20px',
            textAlign: 'center',
            color: 'var(--text-secondary)',
          }}
        >
          <div style={{ fontSize: '2rem', marginBottom: '12px' }}>📊</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
            No Misconceptions Found
          </div>
          <p style={{ margin: 0, fontSize: '0.9rem' }}>
            No accepted conceptual misconception findings recorded for this assessment.
          </p>
        </div>
      )}

      {/* Section 1: Class-Wide Clusters (≥2 Students) */}
      {!loading && clusterData && (
        <div data-testid="class-wide-clusters-section" style={{ marginBottom: '32px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 700, margin: 0 }}>
              Class-Wide Misconception Clusters ({clusterData.clusters.length})
            </h3>
            <span className="badge badge-primary" style={{ fontSize: '0.78rem' }}>
              Minimum 2 Students
            </span>
          </div>

          {clusterData.clusters.length === 0 ? (
            <div className="card" style={{ padding: '24px', color: 'var(--text-secondary)' }}>
              No class-wide clusters currently detected. Single-occurrence misconceptions are listed in the isolated section below.
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '20px' }}>
              {clusterData.clusters.map((cluster) => {
                const cId = cluster.cluster_id;
                const isGenerating = generatingIntervention[cId] || false;
                const result = interventionResults[cId];

                return (
                  <div
                    key={cId}
                    data-testid={`cluster-card-${cId}`}
                    className="card"
                    style={{
                      padding: '20px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '14px',
                      border: '1px solid var(--border-color)',
                      borderRadius: '8px',
                      background: 'var(--bg-secondary)',
                    }}
                  >
                    {/* Header: Concept & Student Count Badge */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                      <h4 style={{ fontSize: '1.1rem', fontWeight: 700, margin: 0, color: '#fca5a5' }}>
                        {cluster.linked_concept}
                      </h4>
                      <span
                        data-testid={`cluster-student-count-${cId}`}
                        className="badge badge-danger"
                        style={{ fontSize: '0.8rem', fontWeight: 600, padding: '4px 8px' }}
                      >
                        {cluster.student_count} Students Affected
                      </span>
                    </div>

                    {/* Hypothesis */}
                    <div style={{ fontSize: '0.9rem', color: 'var(--text-primary)' }}>
                      <strong>Hypothesis:</strong> {cluster.hypothesis}
                    </div>

                    {/* Evidence Excerpts */}
                    {cluster.evidence_excerpts.length > 0 && (
                      <div style={{ background: 'rgba(0, 0, 0, 0.2)', padding: '10px 14px', borderRadius: '6px' }}>
                        <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>
                          Evidence Excerpts ({cluster.evidence_excerpts.length}):
                        </div>
                        <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '0.84rem', color: '#e5e7eb' }}>
                          {cluster.evidence_excerpts.map((exc, i) => (
                            <li key={i} style={{ fontStyle: 'italic', marginBottom: '2px' }}>
                              &ldquo;{exc}&rdquo;
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Severity Distribution */}
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Severity:</span>
                      {cluster.severity_distribution.high > 0 && (
                        <span className="badge badge-danger" style={{ fontSize: '0.72rem' }}>
                          High: {cluster.severity_distribution.high}
                        </span>
                      )}
                      {cluster.severity_distribution.medium > 0 && (
                        <span className="badge badge-warning" style={{ fontSize: '0.72rem' }}>
                          Medium: {cluster.severity_distribution.medium}
                        </span>
                      )}
                      {cluster.severity_distribution.low > 0 && (
                        <span className="badge badge-neutral" style={{ fontSize: '0.72rem' }}>
                          Low: {cluster.severity_distribution.low}
                        </span>
                      )}
                    </div>

                    {/* Recommended Class Intervention */}
                    <div
                      style={{
                        padding: '12px',
                        background: 'rgba(59, 130, 246, 0.08)',
                        borderLeft: '3px solid #3b82f6',
                        borderRadius: '0 4px 4px 0',
                        fontSize: '0.84rem',
                        lineHeight: 1.4,
                      }}
                    >
                      <strong style={{ color: '#93c5fd' }}>Recommended Class Intervention:</strong>
                      <div style={{ marginTop: '4px' }}>{cluster.recommended_intervention}</div>
                    </div>

                    {/* Action Button: Note G (REVISED) */}
                    <div style={{ marginTop: 'auto', paddingTop: '10px' }}>
                      <button
                        type="button"
                        data-testid={`create-intervention-btn-${cId}`}
                        className="btn btn-primary btn-sm"
                        disabled={isGenerating}
                        onClick={() => handleCreateClassIntervention(cluster)}
                        style={{ width: '100%' }}
                      >
                        {isGenerating ? 'Generating Group Interventions...' : '⚡ Create Class Intervention'}
                      </button>

                      {result && (
                        <div
                          data-testid={`intervention-result-${cId}`}
                          className="alert alert-success"
                          style={{ marginTop: '8px', padding: '8px 12px', fontSize: '0.82rem' }}
                        >
                          ✓ {result.message} across {result.totalCount} student finding(s).
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Section 2: Isolated Misconceptions (1 Student) — Note H: Collapsed by default */}
      {!loading && clusterData && (
        <div data-testid="isolated-misconceptions-section" style={{ marginTop: '20px' }}>
          <details
            data-testid="isolated-details-accordion"
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '16px',
            }}
          >
            <summary
              style={{
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: '1rem',
                color: 'var(--text-secondary)',
                userSelect: 'none',
              }}
            >
              ▸ Isolated Misconceptions ({clusterData.isolated.length}) — Single-occurrence findings
            </summary>

            <div style={{ marginTop: '16px' }}>
              {clusterData.isolated.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.88rem' }}>
                  No isolated single-occurrence misconceptions recorded.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {clusterData.isolated.map((item) => (
                    <div
                      key={item.cluster_id}
                      data-testid={`isolated-card-${item.cluster_id}`}
                      style={{
                        padding: '12px 16px',
                        background: 'rgba(0, 0, 0, 0.15)',
                        border: '1px solid var(--border-color)',
                        borderRadius: '6px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        gap: '12px',
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                          {item.linked_concept}
                        </div>
                        <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                          {item.hypothesis}
                        </div>
                        {item.evidence_excerpts.length > 0 && (
                          <div style={{ fontSize: '0.8rem', fontStyle: 'italic', color: '#9ca3af', marginTop: '2px' }}>
                            &ldquo;{item.evidence_excerpts[0]}&rdquo;
                          </div>
                        )}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span className="badge badge-neutral" style={{ fontSize: '0.75rem' }}>
                          Student #{item.student_ids[0]}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </details>
        </div>
      )}
    </div>
  );
};

