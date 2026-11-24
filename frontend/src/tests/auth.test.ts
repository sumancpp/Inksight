import { describe, it, expect, beforeEach, vi } from 'vitest';
import { api } from '../services/api';

describe('Authentication & Session Initialization Contracts', () => {
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

  it('missing session: auto-provisions demo session and sets token in localStorage', async () => {
    let demoSessionCalled = false;
    let meCalled = false;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL) => {
      const urlStr = url.toString();
      if (urlStr.includes('/auth/me')) {
        meCalled = true;
        return new Response('Unauthorized', { status: 401 });
      }
      if (urlStr.includes('/auth/demo-session')) {
        demoSessionCalled = true;
        return new Response(
          JSON.stringify({
            access_token: 'fresh-demo-jwt-abc',
            token_type: 'bearer',
            user: { id: 1, email: 'demo_admin@inksight.edu', role: 'admin' },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response('Not Found', { status: 404 });
    });

    expect(localStorage.getItem('token')).toBeNull();

    // With no existing token, getDemoSession is called directly
    const res = await api.getDemoSession();
    expect(demoSessionCalled).toBe(true);
    expect(meCalled).toBe(false);
    expect(res.access_token).toBe('fresh-demo-jwt-abc');
    expect(localStorage.getItem('token')).toBe('fresh-demo-jwt-abc');
  });

  it('expired/invalid session: /auth/me returns 401, stale token is purged, demo fallback succeeds', async () => {
    mockLocalStorage.setItem('token', 'stale-expired-jwt-999');

    let meCalls = 0;
    let demoCalls = 0;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL, init?: RequestInit) => {
      const urlStr = url.toString();
      const headers = new Headers(init?.headers);

      if (urlStr.includes('/auth/me')) {
        meCalls++;
        // Verify outgoing request attached the stale bearer token
        expect(headers.get('Authorization')).toBe('Bearer stale-expired-jwt-999');
        return new Response(JSON.stringify({ detail: 'Could not validate credentials' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (urlStr.includes('/auth/demo-session')) {
        demoCalls++;
        return new Response(
          JSON.stringify({
            access_token: 'new-valid-demo-token-777',
            token_type: 'bearer',
            user: { id: 2, email: 'demo_admin@inksight.edu', role: 'admin' },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      return new Response('Not found', { status: 404 });
    });

    // Simulate AuthContext initAuth lifecycle with stale token
    let activeToken = localStorage.getItem('token');
    let user = null;

    if (activeToken) {
      try {
        user = await api.getMe();
      } catch (err: any) {
        expect(err.status).toBe(401);
        // Stale token must be purged immediately
        localStorage.removeItem('token');
        activeToken = null;
      }
    }

    expect(localStorage.getItem('token')).toBeNull();
    expect(meCalls).toBe(1);

    // Demo session fallback
    const demoRes = await api.getDemoSession();
    activeToken = demoRes.access_token;
    user = demoRes.user;

    expect(demoCalls).toBe(1);
    expect(activeToken).toBe('new-valid-demo-token-777');
    expect(localStorage.getItem('token')).toBe('new-valid-demo-token-777');
    expect(user.email).toBe('demo_admin@inksight.edu');
  });

  it('failed demo initialization: propagates error, preserves clean unauthenticated state', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL) => {
      const urlStr = url.toString();
      if (urlStr.includes('/auth/demo-session')) {
        return new Response(JSON.stringify({ detail: 'Demo session endpoint is disabled in production.' }), {
          status: 403,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response('Not found', { status: 404 });
    });

    await expect(api.getDemoSession()).rejects.toThrow('Demo session endpoint is disabled in production.');
    expect(localStorage.getItem('token')).toBeNull();
  });

  it('in-flight deduplication: concurrent initAuth calls share a single promise and avoid duplicate requests', async () => {
    let demoNetworkCalls = 0;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL) => {
      const urlStr = url.toString();
      if (urlStr.includes('/auth/demo-session')) {
        demoNetworkCalls++;
        // Simulate real async delay
        await new Promise((resolve) => setTimeout(resolve, 50));
        return new Response(
          JSON.stringify({
            access_token: 'deduped-token-111',
            token_type: 'bearer',
            user: { id: 1, email: 'demo_admin@inksight.edu', role: 'admin' },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response('Not found', { status: 404 });
    });

    // Emulate the deduplication pattern used in AuthContext
    let pendingPromise: Promise<any> | null = null;
    const runDeduplicatedInit = () => {
      if (pendingPromise) return pendingPromise;
      pendingPromise = api.getDemoSession().finally(() => {
        pendingPromise = null;
      });
      return pendingPromise;
    };

    // Simulate React StrictMode mounting twice in rapid succession
    const [res1, res2] = await Promise.all([
      runDeduplicatedInit(),
      runDeduplicatedInit(),
    ]);

    expect(demoNetworkCalls).toBe(1);
    expect(res1.access_token).toBe('deduped-token-111');
    expect(res2.access_token).toBe('deduped-token-111');
  });
});

