import React, { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../services/api';
import { Assessment, LearningTopic } from '../../types';

export const AdminOverviewView: React.FC = () => {
  const { user } = useAuth();
  const [topics, setTopics] = useState<LearningTopic[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadSystemData = async () => {
      setLoading(true);
      try {
        const [tRes, aRes] = await Promise.all([
          api.getTopics(),
          api.getAssessments(),
        ]);
        setTopics(tRes.items);
        setAssessments(aRes.items);
      } catch (err: any) {
        setError(err.message || 'Failed to load system data.');
      } finally {
        setLoading(false);
      }
    };
    loadSystemData();
  }, []);

  if (loading && !topics.length && !assessments.length) {
    return (
      <div className="loading-container">
        <span className="spinner" />
        <p>Loading system overview...</p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Administrator System Overview</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          Overview of platform state, database assets, and administrative access controls.
        </p>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="grid-3" style={{ marginBottom: '24px' }}>
        <div className="card">
          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
            Active Administrator
          </div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700 }}>{user?.full_name}</div>
          <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>{user?.email}</div>
        </div>

        <div className="card">
          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
            Registered Topics
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>{topics.length}</div>
          <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Curriculum Domains</div>
        </div>

        <div className="card">
          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
            Created Assessments
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>{assessments.length}</div>
          <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Diagnostic Tests</div>
        </div>
      </div>

      <div className="card">
        <h3 className="card-title" style={{ marginBottom: '14px' }}>Backend Infrastructure Status</h3>
        <table style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>Subsystem</th>
              <th>Status</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Authentication & RBAC</td>
              <td><span className="badge badge-success">Active</span></td>
              <td>JWT Bearer Tokens, Bcrypt Password Hashing</td>
            </tr>
            <tr>
              <td>OCR Ingestion Pipeline</td>
              <td><span className="badge badge-info">Mock Provider</span></td>
              <td>Deterministic local mock adapter with state machine</td>
            </tr>
            <tr>
              <td>AI Evaluation Engine</td>
              <td><span className="badge badge-info">Mock Provider</span></td>
              <td>Rule-based misconception diagnosis & confidence scoring</td>
            </tr>
            <tr>
              <td>Remediation Generation</td>
              <td><span className="badge badge-info">Mock Provider</span></td>
              <td>Targeted follow-up item generation from accepted findings</td>
            </tr>
            <tr>
              <td>Practice Delivery Runner</td>
              <td><span className="badge badge-success">Production Ready</span></td>
              <td>Safe student delivery, zero teacher secret leakage</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
};
