import React, { useEffect, useState, useRef } from 'react';
import { useAuth } from '../context/AuthContext';

export interface DemoAuthGateProps {
  children: React.ReactNode;
  onRedirect?: (path: string) => void;
}

export const DemoAuthGate: React.FC<DemoAuthGateProps> = ({ children, onRedirect }) => {
  const { token, login } = useAuth();
  const [gateLoading, setGateLoading] = useState<boolean>(false);
  const [gateError, setGateError] = useState<string | null>(null);
  const hasAttemptedRef = useRef<boolean>(false);

  const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true';

  useEffect(() => {
    // If not in demo mode, pass through immediately
    if (!isDemoMode) {
      return;
    }

    // If token already present in storage or context: pass through
    const existingToken = localStorage.getItem('inksight_token') || localStorage.getItem('token') || token;
    if (existingToken) {
      return;
    }

    if (hasAttemptedRef.current) {
      return;
    }
    hasAttemptedRef.current = true;

    const performDemoLogin = async () => {
      setGateLoading(true);
      setGateError(null);
      try {
        const demoEmail = import.meta.env.VITE_DEMO_TEACHER_EMAIL || 'smith@inksight.edu';
        const demoPassword = import.meta.env.VITE_DEMO_TEACHER_PASSWORD || 'teacher123';

        // Authenticate as the seeded demo teacher with fallback support
        try {
          await login(demoEmail, demoPassword);
        } catch (firstErr) {
          const fallbackEmail = demoEmail.includes('inksight')
            ? demoEmail.replace('inksight', 'learngraph')
            : demoEmail.replace('learngraph', 'inksight');
          await login(fallbackEmail, demoPassword);
        }

        // Redirect to /dashboard
        if (onRedirect) {
          onRedirect('/dashboard');
        } else if (typeof window !== 'undefined' && window.location) {
          if (window.location.pathname !== '/dashboard') {
            window.history.pushState({}, '', '/dashboard');
            window.dispatchEvent(new PopStateEvent('popstate'));
          }
        }
      } catch (err: any) {
        console.error('Demo auto-login failed:', err);
        setGateError('Demo auto-login failed. Ensure the seed teacher exists (run backend seed script).');
      } finally {
        setGateLoading(false);
      }
    };

    performDemoLogin();
  }, [isDemoMode, token, login, onRedirect]);

  // Full-page error screen if demo auto-login failed
  if (gateError) {
    return (
      <div
        data-testid="demo-auth-gate-error"
        className="demo-error-screen"
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
          background: 'var(--bg-primary, #f8fafc)',
          color: 'var(--text-primary, #0f172a)',
        }}
      >
        <div
          style={{
            maxWidth: '520px',
            width: '100%',
            background: 'var(--bg-card, #ffffff)',
            padding: '36px',
            borderRadius: '12px',
            border: '1px solid #fca5a5',
            textAlign: 'center',
            boxShadow: '0 20px 25px -5px rgba(15, 23, 42, 0.08)',
          }}
        >
          <div style={{ fontSize: '3rem', marginBottom: '16px' }}>⚠️</div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: '#dc2626', marginBottom: '12px' }}>
            Authentication Failure
          </h2>
          <p
            data-testid="demo-auth-error-message"
            style={{ color: '#475569', fontSize: '1rem', lineHeight: '1.6', marginBottom: '24px' }}
          >
            Demo auto-login failed. Ensure the seed teacher exists (run backend seed script).
          </p>
          <div
            style={{
              background: '#f1f5f9',
              padding: '14px',
              borderRadius: '8px',
              fontSize: '0.85rem',
              fontFamily: 'monospace',
              color: '#0284c7',
              textAlign: 'left',
              wordBreak: 'break-all',
              border: '1px solid #e2e8f0',
            }}
          >
            $ python backend/scripts/seed_cluster_demo.py
          </div>
        </div>
      </div>
    );
  }

  // Full-page loading state while demo login is in progress
  if (gateLoading) {
    return (
      <div
        data-testid="demo-auth-gate-loading"
        className="loading-container"
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--bg-primary, #f8fafc)',
          color: 'var(--text-primary, #0f172a)',
        }}
      >
        <span className="spinner" style={{ width: '36px', height: '36px', marginBottom: '16px' }} />
        <p style={{ fontSize: '1rem', color: '#64748b' }}>Signing in as Demo Teacher...</p>
      </div>
    );
  }

  return <>{children}</>;
};

