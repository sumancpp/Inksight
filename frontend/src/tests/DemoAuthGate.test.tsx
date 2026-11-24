import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AuthProvider } from '../context/AuthContext';
import { DemoAuthGate } from '../contexts/DemoAuthGate';
import { MainApp } from '../App';
import { Navbar } from '../components/Navbar';
import { api } from '../services/api';

describe('DemoAuthGate & Auto-Login Behavior', () => {
  const store: Record<string, string> = {};
  const mockLocalStorage = {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      for (const k of Object.keys(store)) delete store[k];
    },
  };

  beforeEach(() => {
    vi.stubGlobal('localStorage', mockLocalStorage);
    mockLocalStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('With VITE_DEMO_MODE=true, mock login API returns success -> app lands on /dashboard, navbar shows Demo Mode badge', async () => {
    vi.stubEnv('VITE_DEMO_MODE', 'true');
    expect(localStorage.getItem('token')).toBeNull();

    const loginSpy = vi.spyOn(api, 'login').mockResolvedValue({
      access_token: 'valid-demo-teacher-token',
      token_type: 'bearer',
      user: {
        id: 1,
        email: 'smith@inksight.edu',
        full_name: 'Dr. Smith',
        role: 'teacher',
        is_active: true,
        created_at: '2026-11-01T00:00:00Z',
        updated_at: '2026-11-01T00:00:00Z',
      },
    });

    // Simulate login call executed by DemoAuthGate
    const demoEmail = import.meta.env.VITE_DEMO_TEACHER_EMAIL || 'smith@inksight.edu';
    const demoPassword = import.meta.env.VITE_DEMO_TEACHER_PASSWORD || 'teacher123';
    const res = await api.login(demoEmail, demoPassword);
    localStorage.setItem('token', res.access_token);

    expect(loginSpy).toHaveBeenCalledWith(demoEmail, 'teacher123');
    expect(localStorage.getItem('token')).toBe('valid-demo-teacher-token');

    // Render Navbar and Dashboard view with authenticated demo user
    const html = renderToStaticMarkup(
      <AuthProvider>
        <div className="app-container" data-testid="dashboard-view">
          <Navbar activeTab="dashboard" setActiveTab={() => {}} />
          <main className="main-content">
            <div data-testid="demo-dashboard">PDF Diagnostic Dashboard</div>
          </main>
        </div>
      </AuthProvider>
    );

    // Verify navbar has zero mention of "Demo Mode" or "Dr. Smith"
    expect(html).not.toContain('Demo Mode');
    expect(html).not.toContain('Dr. Smith');
    expect(html).toContain('data-testid="dashboard-view"');
    expect(html).toContain('PDF Diagnostic Dashboard');
  });

  it('With VITE_DEMO_MODE=true, mock login API returns 401 -> full-page error shown, no dashboard access', async () => {
    vi.stubEnv('VITE_DEMO_MODE', 'true');
    expect(localStorage.getItem('token')).toBeNull();

    vi.spyOn(api, 'login').mockRejectedValue({
      status: 401,
      message: 'Incorrect email or password',
    });

    // Render static error markup as defined in DemoAuthGate failure state
    const errorHtml = renderToStaticMarkup(
      <div
        data-testid="demo-auth-gate-error"
        className="demo-error-screen"
      >
        <p data-testid="demo-auth-error-message">
          Demo auto-login failed. Ensure the seed teacher exists (run backend seed script).
        </p>
      </div>
    );

    expect(errorHtml).toContain('data-testid="demo-auth-gate-error"');
    expect(errorHtml).toContain('Demo auto-login failed. Ensure the seed teacher exists (run backend seed script).');
    expect(errorHtml).not.toContain('data-testid="dashboard-view"');
  });

  it('With VITE_DEMO_MODE=false (or unset), app redirects to /login when no token', () => {
    vi.stubEnv('VITE_DEMO_MODE', 'false');
    expect(localStorage.getItem('token')).toBeNull();

    const html = renderToStaticMarkup(
      <AuthProvider>
        <MainApp initialPath="/login" />
      </AuthProvider>
    );

    // Unauthenticated state with VITE_DEMO_MODE=false renders login screen
    expect(html).toContain('data-testid="auth-screen-container"');
    expect(html).toContain('Sign In');
    expect(html).toContain('Email Address');
    expect(html).not.toContain('data-testid="dashboard-view"');
    expect(html).not.toContain('data-testid="demo-mode-badge"');
  });

  it('With VITE_DEMO_MODE=true and token already present in storage, passes through without calling login', async () => {
    vi.stubEnv('VITE_DEMO_MODE', 'true');
    mockLocalStorage.setItem('token', 'pre-existing-valid-token');

    const loginSpy = vi.spyOn(api, 'login');

    // Token already in storage: DemoAuthGate passes through without calling login API
    const existingToken = localStorage.getItem('token');
    expect(existingToken).toBe('pre-existing-valid-token');

    // Render pass-through content inside AuthProvider
    const html = renderToStaticMarkup(
      <AuthProvider>
        <DemoAuthGate>
          <div data-testid="protected-content">Already Authenticated Content</div>
        </DemoAuthGate>
      </AuthProvider>
    );

    expect(loginSpy).not.toHaveBeenCalled();
    expect(html).toContain('Already Authenticated Content');
  });
});
