import { describe, it, expect, beforeEach, vi } from 'vitest';
import { api } from '../services/api';

describe('Frontend API Client & Contracts', () => {
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

  it('attaches Bearer token from localStorage to outgoing requests', async () => {
    mockLocalStorage.setItem('token', 'fake-jwt-token-123');

    let capturedHeaders: Headers | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url: RequestInfo | URL, init?: RequestInit) => {
      capturedHeaders = new Headers(init?.headers);
      return new Response(JSON.stringify({ id: 1, email: 'test@inksight.edu' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    await api.getMe();
    expect(capturedHeaders?.get('Authorization')).toBe('Bearer fake-jwt-token-123');
  });

  it('correctly parses FastAPI error detail string', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      return new Response(JSON.stringify({ detail: 'Invalid credentials or inactive user' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    await expect(api.login('bad@user.com', 'wrongpass')).rejects.toThrow(
      'Invalid credentials or inactive user'
    );
  });

  it('correctly parses validation error arrays from 422 Unprocessable Content', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      return new Response(
        JSON.stringify({
          detail: [{ loc: ['body', 'marks'], msg: 'marks must be positive' }],
        }),
        {
          status: 422,
          headers: { 'Content-Type': 'application/json' },
        }
      );
    });

    await expect(
      api.createQuestion(1, {
        topic_id: 1,
        prompt: 'test',
        question_type: 'short_answer',
        marks: -1,
        expected_answer: 'ans',
      })
    ).rejects.toThrow('marks must be positive');
  });

  it('ensures student practice delivery items strictly exclude teacher answer keys and rationales', async () => {
    const mockStudentSession = {
      id: 1,
      submission_id: 10,
      status: 'active',
      started_at: '2026-11-02T12:00:00Z',
      completed_at: null,
      items: [
        {
          id: 101,
          question_type: 'mcq',
          prompt: 'What is the derivative of x^2?',
          options: ['A) 2x', 'B) x', 'C) x^3'],
        },
      ],
      responses: [],
    };

    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      return new Response(JSON.stringify(mockStudentSession), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const session = await api.getPracticeSession(1);
    expect(session.items[0]).toHaveProperty('prompt');
    expect(session.items[0]).toHaveProperty('options');
    // Invariant: Student practice item must NOT contain expected_answer, explanation, or uncertainty_note
    expect(session.items[0]).not.toHaveProperty('expected_answer');
    expect(session.items[0]).not.toHaveProperty('explanation');
    expect(session.items[0]).not.toHaveProperty('teacher_notes');
  });

  it('provisions demo session token and stores in localStorage', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL) => {
      const urlStr = url.toString();
      if (urlStr.includes('/auth/demo-session')) {
        return new Response(
          JSON.stringify({
            access_token: 'demo-signed-jwt-token-xyz',
            token_type: 'bearer',
            user: { id: 99, email: 'demo_admin@inksight.edu', role: 'admin', full_name: 'Demo Admin' },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response('Not found', { status: 404 });
    });

    const res = await api.getDemoSession();
    expect(res.access_token).toBe('demo-signed-jwt-token-xyz');
    expect(mockLocalStorage.getItem('token')).toBe('demo-signed-jwt-token-xyz');
    expect(res.user.role).toBe('admin');
  });

  describe('processDocumentEndToEnd polling & terminal states', () => {
    it('polls status and only requests extraction after terminal extracted state', async () => {
      let pollCount = 0;
      let extractionRequested = false;

      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL) => {
        const urlStr = url.toString();
        if (urlStr.includes('/auth/demo-session')) {
          return new Response(
            JSON.stringify({
              access_token: 'token',
              token_type: 'bearer',
              user: { id: 1, role: 'admin' },
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (urlStr.includes('/assessments')) {
          return new Response(
            JSON.stringify({ items: [{ id: 1, title: 'Demo Exam' }], total: 1 }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (urlStr.includes('/submissions') && !urlStr.includes('answer-sheets') && !urlStr.includes('proposed-answers') && !urlStr.includes('evaluat')) {
          return new Response(
            JSON.stringify({ items: [{ id: 1, assessment_id: 1 }], total: 1 }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (urlStr.includes('/submissions/1/answer-sheets') && !urlStr.includes('process')) {
          return new Response(JSON.stringify({ id: 42, upload_status: 'uploaded' }), {
            status: 201,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        if (urlStr.includes('/answer-sheets/42/processing-status')) {
          pollCount++;
          if (pollCount === 1) {
            return new Response(
              JSON.stringify({ upload_status: 'processing', has_extraction: false }),
              { status: 200, headers: { 'Content-Type': 'application/json' } }
            );
          }
          return new Response(
            JSON.stringify({ upload_status: 'extracted', has_extraction: true }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (urlStr.includes('/answer-sheets/42/process')) {
          return new Response(JSON.stringify({ message: 'Queued', upload_id: 42, status: 'processing' }), {
            status: 202,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        if (urlStr.includes('/answer-sheets/42/extraction')) {
          extractionRequested = true;
          return new Response(
            JSON.stringify({
              upload_id: 42,
              extracted_text: 'Student Newton Answer',
              confidence: 0.98,
              structured_segments: [{ segment_id: 1, text: 'Student Newton Answer', confidence: 0.98 }],
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (urlStr.includes('/proposed-answers')) {
          return new Response(
            JSON.stringify({ proposals: [] }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (urlStr.includes('/evaluat')) {
          return new Response(
            JSON.stringify({
              submission_id: 1,
              runs: [
                {
                  id: 10,
                  submission_id: 1,
                  question_id: 1,
                  evaluator_name: 'vllm',
                  answer_text_snapshot: 'Student Newton Answer',
                  findings: [{ id: 1, category: 'Physics', confidence: 0.95, review_status: 'pending' }],
                  created_at: new Date().toISOString(),
                  updated_at: new Date().toISOString(),
                },
              ],
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        return new Response('Not found', { status: 404 });
      });

      const fakePdf = { name: 'exam.pdf', type: 'application/pdf', size: 100 } as unknown as File;
      const progressUpdates: string[] = [];
      const result = await api.processDocumentEndToEnd(fakePdf, (msg) => progressUpdates.push(msg));

      expect(pollCount).toBe(2);
      expect(extractionRequested).toBe(true);
      expect(result.extraction.extracted_text).toBe('Student Newton Answer');
      expect(result.evaluation.submission_id).toBe(1);
      expect(result.evaluation.runs.length).toBe(1);
      expect(progressUpdates).toContain('Uploading PDF document...');
    });

    it('rejects with safe actionable error if processing status fails without calling extraction', async () => {
      let extractionRequested = false;

      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL) => {
        const urlStr = url.toString();
        if (urlStr.includes('/auth/demo-session')) {
          return new Response(
            JSON.stringify({ access_token: 'tok', token_type: 'bearer', user: { id: 1 } }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (urlStr.includes('/assessments')) {
          return new Response(
            JSON.stringify({ items: [{ id: 1, title: 'Demo Exam' }], total: 1 }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (urlStr.includes('/submissions') && !urlStr.includes('answer-sheets')) {
          return new Response(
            JSON.stringify({ items: [{ id: 1, assessment_id: 1 }], total: 1 }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (urlStr.includes('/submissions/1/answer-sheets') && !urlStr.includes('process')) {
          return new Response(JSON.stringify({ id: 50, upload_status: 'uploaded' }), {
            status: 201,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        if (urlStr.includes('/answer-sheets/50/processing-status')) {
          return new Response(
            JSON.stringify({
              upload_status: 'failed',
              has_extraction: false,
              latest_error_code: 'CORRUPTED_DOCUMENT',
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (urlStr.includes('/answer-sheets/50/process')) {
          return new Response(JSON.stringify({ status: 'processing' }), {
            status: 202,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        if (urlStr.includes('/answer-sheets/50/extraction')) {
          extractionRequested = true;
          return new Response('Should not be called', { status: 500 });
        }
        return new Response('Not found', { status: 404 });
      });

      const fakeImg = { name: 'scan.png', type: 'image/png', size: 100 } as unknown as File;
      await expect(api.processDocumentEndToEnd(fakeImg)).rejects.toThrow(
        'OCR processing failed with error code: CORRUPTED_DOCUMENT'
      );
      expect(extractionRequested).toBe(false);
    });

    it('handles incremental page progress reporting during polling', async () => {
      let pollCount = 0;
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL) => {
        const urlStr = url.toString();
        if (urlStr.includes('/auth/demo-session')) {
          return new Response(JSON.stringify({ access_token: 'tok', token_type: 'bearer', user: { id: 1 } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
        if (urlStr.includes('/assessments')) {
          return new Response(JSON.stringify({ items: [{ id: 1, title: 'Demo' }], total: 1 }), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
        if (urlStr.includes('/submissions') && !urlStr.includes('answer-sheets') && !urlStr.includes('proposed-answers') && !urlStr.includes('evaluat')) {
          return new Response(JSON.stringify({ items: [{ id: 1, assessment_id: 1 }], total: 1 }), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
        if (urlStr.includes('/submissions/1/answer-sheets') && !urlStr.includes('process')) {
          return new Response(JSON.stringify({ id: 60, upload_status: 'uploaded' }), { status: 201, headers: { 'Content-Type': 'application/json' } });
        }
        if (urlStr.includes('/answer-sheets/60/processing-status')) {
          pollCount++;
          if (pollCount === 1) {
            return new Response(
              JSON.stringify({
                upload_status: 'processing',
                has_extraction: false,
                pages_completed: 10,
                total_pages: 50,
                progress_percent: 20.0,
              }),
              { status: 200, headers: { 'Content-Type': 'application/json' } }
            );
          }
          return new Response(
            JSON.stringify({
              upload_status: 'extracted',
              has_extraction: true,
              pages_completed: 50,
              total_pages: 50,
              progress_percent: 100.0,
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (urlStr.includes('/answer-sheets/60/process')) {
          return new Response(JSON.stringify({ status: 'processing' }), { status: 202, headers: { 'Content-Type': 'application/json' } });
        }
        if (urlStr.includes('/answer-sheets/60/extraction')) {
          return new Response(
            JSON.stringify({
              upload_id: 60,
              extracted_text: 'Done',
              structured_segments: [],
              confidence: 0.9,
              has_math_content: false,
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (urlStr.includes('/proposed-answers')) {
          return new Response(JSON.stringify({ proposals: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
        if (urlStr.includes('/evaluat')) {
          return new Response(JSON.stringify({ submission_id: 1, runs: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
        return new Response('Not found', { status: 404 });
      });

      const fakePdf = { name: 'multi.pdf', type: 'application/pdf', size: 100 } as unknown as File;
      const reportedProgress: any[] = [];
      const result = await api.processDocumentEndToEnd(fakePdf, (_msg, _step, prog) => {
        if (prog) reportedProgress.push(prog);
      });

      expect(result.extraction.extracted_text).toBe('Done');
      const pageProg = reportedProgress.find((p) => p.totalPages === 50);
      expect(pageProg).toBeDefined();
      expect(pageProg?.totalPages).toBe(50);
    });

    it('allows client cancellation via AbortSignal without requesting extraction', async () => {
      let extractionCalled = false;
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL) => {
        const urlStr = url.toString();
        if (urlStr.includes('/auth/demo-session')) {
          return new Response(JSON.stringify({ access_token: 'tok', token_type: 'bearer', user: { id: 1 } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
        if (urlStr.includes('/assessments')) {
          return new Response(JSON.stringify({ items: [{ id: 1, title: 'Demo' }], total: 1 }), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
        if (urlStr.includes('/submissions') && !urlStr.includes('answer-sheets')) {
          return new Response(JSON.stringify({ items: [{ id: 1, assessment_id: 1 }], total: 1 }), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
        if (urlStr.includes('/submissions/1/answer-sheets') && !urlStr.includes('process')) {
          return new Response(JSON.stringify({ id: 70, upload_status: 'uploaded' }), { status: 201, headers: { 'Content-Type': 'application/json' } });
        }
        if (urlStr.includes('/answer-sheets/70/processing-status')) {
          return new Response(
            JSON.stringify({ upload_status: 'processing', has_extraction: false, pages_completed: 2, total_pages: 80 }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (urlStr.includes('/answer-sheets/70/process')) {
          return new Response(JSON.stringify({ status: 'processing' }), { status: 202, headers: { 'Content-Type': 'application/json' } });
        }
        if (urlStr.includes('/answer-sheets/70/extraction')) {
          extractionCalled = true;
          return new Response('Should not be called', { status: 500 });
        }
        return new Response('Not found', { status: 404 });
      });

      const controller = new AbortController();
      const fakePdf = { name: 'large.pdf', type: 'application/pdf', size: 100 } as unknown as File;

      // Abort after 50ms
      setTimeout(() => controller.abort(), 50);

      await expect(
        api.processDocumentEndToEnd(fakePdf, undefined, { signal: controller.signal })
      ).rejects.toThrow('Client polling was stopped by user');

      expect(extractionCalled).toBe(false);
    });
  });

  describe('Teacher Review Workflow & APIs', () => {
    it('approves a proposed answer with teacher notes', async () => {
      let capturedBody: any;
      let capturedUrl = '';
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedBody = JSON.parse(init?.body as string);
        return new Response(
          JSON.stringify({
            proposal: { id: 10, status: 'approved' },
            review: { id: 1, action: 'approved' },
            authoritative_answer_text: 'Student wrote 2x',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      });

      const res = await api.approveProposal(10, { question_id: 2, review_notes: 'Verified answer match' });
      expect(capturedUrl).toContain('/api/v1/proposed-answers/10/approve');
      expect(capturedBody).toEqual({ question_id: 2, review_notes: 'Verified answer match' });
      expect(res.proposal.status).toBe('approved');
    });

    it('corrects a proposed answer with edited text and question assignment', async () => {
      let capturedBody: any;
      let capturedUrl = '';
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedBody = JSON.parse(init?.body as string);
        return new Response(
          JSON.stringify({
            proposal: { id: 15, status: 'corrected', corrected_text: 'F = m*a' },
            review: { id: 2, action: 'corrected' },
            authoritative_answer_text: 'F = m*a',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      });

      const res = await api.correctProposal(15, 3, 'F = m*a', 'Fixed OCR misread of multiplication');
      expect(capturedUrl).toContain('/api/v1/proposed-answers/15/correct');
      expect(capturedBody).toEqual({
        question_id: 3,
        corrected_text: 'F = m*a',
        review_notes: 'Fixed OCR misread of multiplication',
      });
      expect(res.proposal.status).toBe('corrected');
      expect(res.authoritative_answer_text).toBe('F = m*a');
    });

    it('rejects a proposed answer with reason', async () => {
      let capturedBody: any;
      let capturedUrl = '';
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL, init?: RequestInit) => {
        capturedUrl = url.toString();
        capturedBody = JSON.parse(init?.body as string);
        return new Response(
          JSON.stringify({
            proposal: { id: 20, status: 'rejected', rejection_reason: 'Illegible scribble' },
            review: { id: 3, action: 'rejected' },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      });

      const res = await api.rejectProposal(20, 'Illegible scribble', 'Review notes');
      expect(capturedUrl).toContain('/api/v1/proposed-answers/20/reject');
      expect(capturedBody).toEqual({
        rejection_reason: 'Illegible scribble',
        review_notes: 'Review notes',
      });
      expect(res.proposal.status).toBe('rejected');
    });

    it('reviews evaluation findings with accepted, needs_revision, and rejected actions', async () => {
      const calls: Array<{ url: string; body: any }> = [];
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL, init?: RequestInit) => {
        const body = JSON.parse(init?.body as string);
        calls.push({ url: url.toString(), body });
        return new Response(
          JSON.stringify({
            finding: { id: 5, review_status: body.action, review_notes: body.review_notes },
            audit: { id: 1, action: body.action },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      });

      await api.reviewFinding(5, 'accepted', 'Valid calculus misconception');
      await api.reviewFinding(5, 'needs_revision', 'Check if procedural error instead');
      await api.reviewFinding(5, 'rejected', 'False positive');

      expect(calls).toHaveLength(3);
      expect(calls[0].url).toContain('/api/v1/evaluations/findings/5/review');
      expect(calls[0].body).toEqual({ action: 'accepted', review_notes: 'Valid calculus misconception' });
      expect(calls[1].body).toEqual({ action: 'needs_revision', review_notes: 'Check if procedural error instead' });
      expect(calls[2].body).toEqual({ action: 'rejected', review_notes: 'False positive' });
    });

    it('triggers targeted remediation generation for accepted findings', async () => {
      let capturedUrl = '';
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL) => {
        capturedUrl = url.toString();
        return new Response(
          JSON.stringify({
            id: 1,
            finding_id: 8,
            items: [{ id: 101, question_text: 'Practice Q1', review_status: 'pending_review' }],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      });

      const res = await api.generateRemediationsForFinding(8);
      expect(capturedUrl).toContain('/api/v1/findings/8/remediation/generate');
      expect(res.items).toHaveLength(1);
    });

    it('reviews, edits, and approves remediation items for student delivery', async () => {
      const capturedCalls: Array<{ url: string; body: any }> = [];
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL, init?: RequestInit) => {
        const body = JSON.parse(init?.body as string);
        capturedCalls.push({ url: url.toString(), body });
        return new Response(
          JSON.stringify({
            item: { id: 42, review_status: body.action === 'edit' ? 'edited' : body.action },
            audit: { id: 1, action: body.action },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      });

      // 1. Approve
      await api.reviewRemediationItem(42, 'approve');
      expect(capturedCalls[0].url).toContain('/api/v1/remediations/items/42/review');
      expect(capturedCalls[0].body).toEqual({
        action: 'approve',
        edited_question_text: undefined,
        edited_answer_key: undefined,
        review_notes: undefined,
      });

      // 2. Edit & Approve
      await api.reviewRemediationItem(42, 'edit', {
        edited_question_text: 'Differentiate f(x) = 3x^2',
        edited_answer_key: '6x',
        review_notes: 'Simplified exponent for reinforcement',
      });
      expect(capturedCalls[1].body).toEqual({
        action: 'edit',
        edited_question_text: 'Differentiate f(x) = 3x^2',
        edited_answer_key: '6x',
        review_notes: 'Simplified exponent for reinforcement',
      });

      // 3. Reject
      await api.reviewRemediationItem(42, 'reject');
      expect(capturedCalls[2].body.action).toBe('reject');
    });

    it('safely surfaces review API error without crashing or swallowing', async () => {
      vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
        return new Response(
          JSON.stringify({ detail: 'Invalid review transition: accepted -> pending_review' }),
          { status: 409, headers: { 'Content-Type': 'application/json' } }
        );
      });

      await expect(api.reviewFinding(12, 'needs_revision')).rejects.toThrow(
        'Invalid review transition: accepted -> pending_review'
      );
    });
  });

  describe('Intervention Outcome Tracking and Student Progress', () => {
    it('fetches submission intervention outcomes for teachers', async () => {
      let capturedUrl = '';
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL) => {
        capturedUrl = url.toString();
        return new Response(
          JSON.stringify({
            submission_id: 10,
            assessment_id: 2,
            total_interventions: 2,
            improved_count: 1,
            uncertain_count: 1,
            persisting_gap_count: 0,
            pending_count: 0,
            outcomes: [
              {
                finding_id: 1,
                run_id: 1,
                question_id: 1,
                concept_name: 'Product Rule',
                student_id: 42,
                prior_category: 'misconception',
                prior_confidence: 0.85,
                remediation_items_count: 2,
                evidence_count: 2,
                correct_count: 2,
                accuracy_percentage: 100.0,
                outcome_status: 'improved',
                outcome_label: 'Demonstrated Improvement',
                uncertainty_level: 'Low-Moderate',
                uncertainty_rationale: 'Multiple consistent correct answers.',
                performance_comparison: 'Resolved prior misconception.',
                recommended_action: 'Advance to quotient rule.',
                followup_responses: [],
              },
            ],
            pedagogical_disclaimer: 'Formative verification only.',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      });

      const res = await api.getSubmissionInterventionOutcomes(10);
      expect(capturedUrl).toContain('/api/v1/submissions/10/intervention-outcomes');
      expect(res.submission_id).toBe(10);
      expect(res.improved_count).toBe(1);
      expect(res.outcomes[0].concept_name).toBe('Product Rule');
    });

    it('fetches assessment intervention outcomes for teacher cohorts', async () => {
      let capturedUrl = '';
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL) => {
        capturedUrl = url.toString();
        return new Response(
          JSON.stringify({
            submission_id: 0,
            assessment_id: 5,
            total_interventions: 1,
            improved_count: 0,
            uncertain_count: 1,
            persisting_gap_count: 0,
            pending_count: 0,
            outcomes: [],
            pedagogical_disclaimer: 'Cohort outcomes',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      });

      const res = await api.getAssessmentInterventionOutcomes(5);
      expect(capturedUrl).toContain('/api/v1/assessments/5/intervention-outcomes');
      expect(res.assessment_id).toBe(5);
    });

    it('fetches sanitized student progress report without leaking teacher answers', async () => {
      let capturedUrl = '';
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (url: RequestInfo | URL) => {
        capturedUrl = url.toString();
        return new Response(
          JSON.stringify({
            submission_id: 7,
            assessment_id: 1,
            total_concepts_tracked: 1,
            improved_count: 0,
            uncertain_count: 1,
            persisting_gap_count: 0,
            pending_count: 0,
            concepts: [
              {
                concept_name: 'Integration by Parts',
                baseline_diagnostic_gap: 'Struggled with u-substitution',
                evidence_count: 1,
                correct_count: 1,
                accuracy_percentage: 100.0,
                outcome_status: 'uncertain',
                status_label: 'Tentative Progress (Single Response)',
                uncertainty_level: 'Moderate-High',
                uncertainty_rationale: 'Single practice response is insufficient to declare mastery.',
                recommended_next_step: 'Practice 1-2 more questions.',
                followup_responses: [
                  {
                    item_id: 101,
                    question_type: 'mcq',
                    student_answer: 'B',
                    is_correct: true,
                    score: 1.0,
                    feedback: 'Correct application of formula.',
                    submitted_at: '2026-11-04T12:00:00Z',
                  },
                ],
              },
            ],
            overall_next_step: 'Complete further practice.',
            pedagogical_disclaimer: 'Educational feedback only.',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      });

      const res = await api.getStudentProgressReport(7);
      expect(capturedUrl).toContain('/api/v1/submissions/7/student-progress');
      expect(res.concepts[0].outcome_status).toBe('uncertain');
      expect(res.concepts[0].uncertainty_rationale).toContain('Single practice response is insufficient');

      // Verify strict privacy: ensure teacher keys / rationale are not in student data
      const jsonStr = JSON.stringify(res);
      expect(jsonStr).not.toContain('teacher_answer_key');
      expect(jsonStr).not.toContain('teacher_rationale');
      expect(jsonStr).not.toContain('review_notes');
    });
  });
});
