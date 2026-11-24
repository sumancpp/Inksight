import {
  AnswerMatchingResponse,
  AnswerSheetUpload,
  Assessment,
  AsyncTaskAcceptedResponse,
  EvaluationFinding,
  CorrectionFieldName,
  FindingCorrection,
  FindingReviewStatus,
  FollowUpQuestion,
  InferredQAItem,
  InferredQAResponse,
  InferredQAUpdateRequest,
  InterventionOutcomesSummary,
  LearningTopic,
  LoginResponse,
  OCRExtraction,
  OCRProcessTriggerResponse,
  PaginatedResponse,
  PracticeSessionSummary,
  ProcessingStatusRead,
  ProposedAnswer,
  PendingReviewQueueResponse,
  MisconceptionClusterResponse,
  Question,
  QuestionType,
  RemediationItemTeacherRead,
  StudentPracticeSessionRead,
  StudentProgressReport,
  Submission,
  SubmissionEvaluationSummary,
  TaskStatusResponse,
  User,
  UserRole,
} from '../types';

const rawBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
const API_BASE_URL = rawBaseUrl.endsWith('/api/v1') ? rawBaseUrl.slice(0, -7) : rawBaseUrl;

class ApiError extends Error {
  status: number;
  data: any;

  constructor(status: number, message: string, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const rawToken = localStorage.getItem('inksight_token') || localStorage.getItem('token');
  const token = rawToken?.trim().replace(/^"(.*)"$/, '$1');
  const headers = new Headers(options.headers || {});

  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  if (options.body instanceof FormData) {
    // Requirement 1: Let the browser set the boundary automatically; remove any hardcoded Content-Type
    if (headers.has('Content-Type')) {
      headers.delete('Content-Type');
    }
  } else if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const url = `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
    });
  } catch (err: any) {
    if (err instanceof TypeError && err.message?.toLowerCase().includes('fetch')) {
      throw new ApiError(
        0,
        `Network error when requesting ${url}: Backend unreachable or CORS blocked. Ensure backend is running at ${API_BASE_URL} and origins are permitted.`,
        err
      );
    }
    throw err;
  }

  if (response.status === 204) {
    return {} as T;
  }

  let data: any;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status} ${response.statusText}`;
    if (data) {
      if (typeof data.detail === 'string') {
        errorMessage = data.detail;
      } else if (Array.isArray(data.detail)) {
        errorMessage = data.detail.map((err: any) => err.msg || JSON.stringify(err)).join(', ');
      } else if (data.message) {
        errorMessage = data.message;
      }
    }
    throw new ApiError(response.status, errorMessage, data);
  }

  return data as T;
}

export interface ProcessingProgressInfo {
  statusText: string;
  step: number;
  uploadId?: number;
  pagesCompleted?: number | null;
  totalPages?: number | null;
  progressPercent?: number | null;
}

export const api = {
  // Auth
  async getDemoSession(): Promise<LoginResponse> {
    const res = await request<LoginResponse>('/api/v1/auth/demo-session', {
      method: 'POST',
    });
    if (res.access_token) {
      localStorage.setItem('inksight_token', res.access_token);
      localStorage.setItem('token', res.access_token);
    }
    return res;
  },

  async login(email: string, password: string): Promise<LoginResponse> {
    return request<LoginResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  async register(
    email: string,
    password: string,
    fullName: string,
    role: UserRole
  ): Promise<User> {
    return request<User>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        email,
        password,
        full_name: fullName,
        role,
      }),
    });
  },

  async getMe(): Promise<User> {
    return request<User>('/api/v1/auth/me');
  },

  // Topics
  async getTopics(page = 1, size = 50): Promise<PaginatedResponse<LearningTopic>> {
    const offset = (page - 1) * size;
    return request<PaginatedResponse<LearningTopic>>(`/api/v1/topics?limit=${size}&offset=${offset}`);
  },

  async createTopic(name: string, description?: string): Promise<LearningTopic> {
    return request<LearningTopic>('/api/v1/topics', {
      method: 'POST',
      body: JSON.stringify({ name, description }),
    });
  },

  // Assessments
  async getAssessments(page = 1, size = 50): Promise<PaginatedResponse<Assessment>> {
    const offset = (page - 1) * size;
    return request<PaginatedResponse<Assessment>>(`/api/v1/assessments?limit=${size}&offset=${offset}`);
  },

  async getAssessment(id: number): Promise<Assessment> {
    return request<Assessment>(`/api/v1/assessments/${id}`);
  },

  async createAssessment(title: string, description?: string): Promise<Assessment> {
    return request<Assessment>('/api/v1/assessments', {
      method: 'POST',
      body: JSON.stringify({ title, description }),
    });
  },

  async getQuestions(assessmentId: number): Promise<PaginatedResponse<Question>> {
    return request<PaginatedResponse<Question>>(`/api/v1/assessments/${assessmentId}/questions`);
  },

  async createQuestion(
    assessmentId: number,
    data: {
      topic_id: number;
      prompt: string;
      question_type: QuestionType;
      marks: number;
      expected_answer: string;
      rubric?: string;
    }
  ): Promise<Question> {
    return request<Question>(`/api/v1/assessments/${assessmentId}/questions`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async uploadQuestionPaper(assessmentId: number, file: File, topicId?: number): Promise<Question[]> {
    const formData = new FormData();
    formData.append('file', file);
    const query = topicId ? `?topic_id=${topicId}` : '';
    return request<Question[]>(`/api/v1/assessments/${assessmentId}/upload-question-paper${query}`, {
      method: 'POST',
      body: formData,
    });
  },

  async generateReferenceKeys(assessmentId: number, force = true): Promise<Question[]> {
    return request<Question[]>(`/api/v1/assessments/${assessmentId}/generate-reference-keys?force=${force}`, {
      method: 'POST',
    });
  },

  async approveReferenceKey(
    assessmentId: number,
    questionId: number,
    data: { expected_answer?: string; rubric?: string }
  ): Promise<Question> {
    return request<Question>(`/api/v1/assessments/${assessmentId}/questions/${questionId}/approve-reference`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // Submissions
  async getSubmissions(assessmentId: number): Promise<PaginatedResponse<Submission>> {
    return request<PaginatedResponse<Submission>>(`/api/v1/assessments/${assessmentId}/submissions`);
  },

  async getSubmission(id: number): Promise<Submission> {
    return request<Submission>(`/api/v1/submissions/${id}`);
  },

  async createSubmission(assessmentId: number): Promise<Submission> {
    return request<Submission>(`/api/v1/assessments/${assessmentId}/submissions`, {
      method: 'POST',
      body: JSON.stringify({ status: 'submitted' }),
    });
  },

  // Answer Sheet Uploads & OCR
  async uploadAnswerSheet(submissionId: number, file: File): Promise<AnswerSheetUpload> {
    const formData = new FormData();
    formData.append('file', file);
    return request<AnswerSheetUpload>(`/api/v1/submissions/${submissionId}/answer-sheets`, {
      method: 'POST',
      body: formData,
    });
  },

  async getAnswerSheets(submissionId: number): Promise<PaginatedResponse<AnswerSheetUpload>> {
    return request<PaginatedResponse<AnswerSheetUpload>>(`/api/v1/submissions/${submissionId}/answer-sheets`);
  },

  async triggerOCRProcess(uploadId: number, force: boolean = false): Promise<OCRProcessTriggerResponse> {
    const query = force ? '?force=true' : '';
    return request<OCRProcessTriggerResponse>(`/api/v1/answer-sheets/${uploadId}/process${query}`, {
      method: 'POST',
    });
  },

  async getOCRProcessingStatus(uploadId: number): Promise<ProcessingStatusRead> {
    return request<ProcessingStatusRead>(`/api/v1/answer-sheets/${uploadId}/processing-status`);
  },

  async getOCRExtraction(uploadId: number): Promise<OCRExtraction> {
    return request<OCRExtraction>(`/api/v1/answer-sheets/${uploadId}/extraction`);
  },

  // Matching & Review
  async matchUploadAnswers(uploadId: number, assessmentId?: number): Promise<AnswerMatchingResponse> {
    const query = assessmentId ? `?assessment_id=${assessmentId}` : '';
    return request<AnswerMatchingResponse>(`/api/v1/answer-sheets/${uploadId}/match-answers${query}`, {
      method: 'POST',
    });
  },

  async getUploadProposedAnswers(uploadId: number): Promise<AnswerMatchingResponse> {
    return request<AnswerMatchingResponse>(`/api/v1/answer-sheets/${uploadId}/proposed-answers`);
  },

  // Answer-Sheet-Only Mode (Zero Question Paper)
  async inferQuestionsFromAnswerSheet(uploadId: number, difficulty?: string): Promise<InferredQAResponse> {
    const query = difficulty ? `?difficulty=${encodeURIComponent(difficulty)}` : '';
    try {
      return await request<InferredQAResponse>(`/api/v1/answer-sheets/${uploadId}/infer-questions${query}`, {
        method: 'POST',
      });
    } catch (err: any) {
      if (
        (err instanceof TypeError && err.message?.toLowerCase().includes('fetch')) ||
        (err instanceof ApiError && err.status === 0)
      ) {
        throw new ApiError(
          0,
          `Failed to infer questions: Backend unreachable or CORS blocked at /api/v1/answer-sheets/${uploadId}/infer-questions. Please verify backend server is running.`,
          err
        );
      }
      throw err;
    }
  },

  async updateInferredQuestion(
    uploadId: number,
    questionId: number,
    data: InferredQAUpdateRequest
  ): Promise<InferredQAItem> {
    return request<InferredQAItem>(`/api/v1/answer-sheets/${uploadId}/inferred-questions/${questionId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  async createZeroQPContext(filename?: string): Promise<{
    assessment_id: number;
    submission_id: number;
    assessment_title: string;
  }> {
    const query = filename ? `?filename=${encodeURIComponent(filename)}` : '';
    return request<any>(`/api/v1/answer-sheets/zero-qp-context${query}`, {
      method: 'POST',
    });
  },

  async getProposedAnswers(submissionId: number): Promise<AnswerMatchingResponse> {
    return request<AnswerMatchingResponse>(`/api/v1/submissions/${submissionId}/proposed-answers`);
  },

  async approveProposal(
    proposalId: number,
    options?: { question_id?: number; review_notes?: string } | string
  ): Promise<any> {
    const body: { question_id?: number; review_notes?: string } = {};
    if (typeof options === 'string') {
      body.review_notes = options;
    } else if (options) {
      if (options.question_id !== undefined) body.question_id = options.question_id;
      if (options.review_notes !== undefined) body.review_notes = options.review_notes;
    }
    return request<any>(`/api/v1/proposed-answers/${proposalId}/approve`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  async correctProposal(
    proposalId: number,
    questionId: number | undefined,
    correctedText: string,
    reviewNotes?: string
  ): Promise<any> {
    const body: { corrected_text: string; question_id?: number; review_notes?: string } = {
      corrected_text: correctedText,
    };
    if (questionId !== undefined) body.question_id = questionId;
    if (reviewNotes !== undefined) body.review_notes = reviewNotes;
    return request<any>(`/api/v1/proposed-answers/${proposalId}/correct`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  async rejectProposal(
    proposalId: number,
    reason?: string,
    reviewNotes?: string
  ): Promise<any> {
    return request<any>(`/api/v1/proposed-answers/${proposalId}/reject`, {
      method: 'POST',
      body: JSON.stringify({
        rejection_reason: reason || 'Rejected by reviewer',
        review_notes: reviewNotes,
      }),
    });
  },

  // Background Task Queue & Async Evaluations
  async triggerAsyncEvaluation(submissionId: number): Promise<AsyncTaskAcceptedResponse> {
    return request<AsyncTaskAcceptedResponse>(`/api/v1/submissions/${submissionId}/evaluate`, {
      method: 'POST',
    });
  },

  async getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
    return request<TaskStatusResponse>(`/api/v1/submissions/task-status/${taskId}`);
  },

  async pollTaskUntilComplete(
    taskId: string,
    onProgress?: (statusText: string) => void,
    pollIntervalMs: number = 3000,
    maxWaitMs: number = 300000
  ): Promise<TaskStatusResponse> {
    const startTime = Date.now();
    while (Date.now() - startTime < maxWaitMs) {
      const task = await this.getTaskStatus(taskId);
      if (task.status === 'SUCCESS') {
        return task;
      }
      if (task.status === 'FAILURE') {
        throw new Error(task.error || 'Background task failed during execution.');
      }
      const stepMsg = task.result?.step || `Processing OCR... Analyzing... (${task.status})`;
      if (onProgress) {
        onProgress(stepMsg);
      }
      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
    }
    throw new Error('Background task polling timed out.');
  },

  async sendResultsEmail(
    submissionId: number,
    recipientEmail?: string
  ): Promise<{ status: string; submission_id: number; recipient_email: string; message: string }> {
    const query = recipientEmail ? `?recipient_email=${encodeURIComponent(recipientEmail)}` : '';
    return request(`/api/v1/results/${submissionId}/email${query}`, {
      method: 'POST',
    });
  },

  // Evaluations
  async evaluateSubmission(submissionId: number): Promise<SubmissionEvaluationSummary> {
    try {
      const accepted = await this.triggerAsyncEvaluation(submissionId);
      if (accepted && accepted.task_id) {
        await this.pollTaskUntilComplete(accepted.task_id);
      }
    } catch (err: any) {
      console.warn('Async evaluation fallback or error:', err);
    }
    return this.getSubmissionEvaluations(submissionId);
  },

  async getSubmissionEvaluations(submissionId: number): Promise<SubmissionEvaluationSummary> {
    return request<SubmissionEvaluationSummary>(`/api/v1/submissions/${submissionId}/evaluations`);
  },

  async reviewFinding(
    findingId: number,
    action: FindingReviewStatus | 'accepted' | 'rejected' | 'needs_revision',
    reviewNotes?: string,
    acknowledgeUncertainty?: boolean
  ): Promise<EvaluationFinding> {
    const normalizedAction =
      action === 'pending' || action === 'pending_review'
        ? 'needs_revision'
        : action;
    const body: Record<string, any> = {
      action: normalizedAction,
      review_notes: reviewNotes,
    };
    if (acknowledgeUncertainty !== undefined) {
      body.acknowledge_uncertainty = acknowledgeUncertainty;
    }
    return request<EvaluationFinding>(`/api/v1/evaluations/findings/${findingId}/review`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  // Follow-up Question Verification
  async proposeFollowUp(findingId: number): Promise<FollowUpQuestion> {
    return request<FollowUpQuestion>(`/api/v1/evaluations/findings/${findingId}/follow-up/propose`, {
      method: 'POST',
    });
  },

  async approveFollowUp(followUpId: number, auditNotes?: string): Promise<FollowUpQuestion> {
    return request<FollowUpQuestion>(`/api/v1/evaluations/follow-ups/${followUpId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ audit_notes: auditNotes }),
    });
  },

  async rejectFollowUp(followUpId: number, reason: string): Promise<FollowUpQuestion> {
    return request<FollowUpQuestion>(`/api/v1/evaluations/follow-ups/${followUpId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  },

  async getFollowUpsForFinding(findingId: number): Promise<FollowUpQuestion[]> {
    return request<FollowUpQuestion[]>(`/api/v1/evaluations/findings/${findingId}/follow-ups`);
  },

  // Finding Corrections
  async applyCorrection(
    findingId: number,
    fieldName: CorrectionFieldName,
    correctedValue: any,
    correctionReason: string
  ): Promise<FindingCorrection> {
    return request<FindingCorrection>(`/api/v1/evaluations/findings/${findingId}/corrections`, {
      method: 'POST',
      body: JSON.stringify({
        field_name: fieldName,
        corrected_value: correctedValue,
        correction_reason: correctionReason,
      }),
    });
  },

  async revertCorrection(findingId: number, correctionId: number): Promise<FindingCorrection> {
    return request<FindingCorrection>(
      `/api/v1/evaluations/findings/${findingId}/corrections/${correctionId}/revert`,
      { method: 'POST' }
    );
  },

  async getCorrectionsForFinding(findingId: number): Promise<FindingCorrection[]> {
    return request<FindingCorrection[]>(`/api/v1/evaluations/findings/${findingId}/corrections`);
  },

  // Confidence-Aware Teacher Review Queue
  async getPendingReviewQueue(params?: {
    assessment_id?: number;
    page?: number;
    page_size?: number;
    sort?: string;
  }): Promise<PendingReviewQueueResponse> {
    const q = new URLSearchParams();
    if (params?.assessment_id) q.set('assessment_id', String(params.assessment_id));
    if (params?.page) q.set('page', String(params.page));
    if (params?.page_size) q.set('page_size', String(params.page_size));
    if (params?.sort) q.set('sort', params.sort);
    const queryString = q.toString() ? `?${q.toString()}` : '';
    return request<PendingReviewQueueResponse>(`/api/v1/evaluations/pending-review${queryString}`);
  },

  // Class-Level Misconception Clusters
  async getMisconceptionClusters(assessmentId: number): Promise<MisconceptionClusterResponse> {
    return request<MisconceptionClusterResponse>(
      `/api/v1/analytics/assessments/${assessmentId}/misconception-clusters`
    );
  },

  // Remediation
  async generateRemediationsForFinding(findingId: number, generatorName?: string): Promise<any> {
    const query = generatorName ? `?generator_name=${encodeURIComponent(generatorName)}` : '';
    return request<any>(`/api/v1/findings/${findingId}/remediation/generate${query}`, {
      method: 'POST',
    });
  },

  async getRemediationItemsForSubmission(
    submissionId: number
  ): Promise<RemediationItemTeacherRead[]> {
    return request<RemediationItemTeacherRead[]>(`/api/v1/submissions/${submissionId}/remediations`);
  },

  async getRemediationItemsForFinding(
    findingId: number
  ): Promise<RemediationItemTeacherRead[]> {
    return request<RemediationItemTeacherRead[]>(`/api/v1/findings/${findingId}/remediations`);
  },

  async reviewRemediationItem(
    itemId: number,
    action: string,
    edits?: {
      edited_question_text?: string;
      edited_answer_key?: string;
      edited_expected_answer?: string;
      edited_explanation?: string;
      review_notes?: string;
    }
  ): Promise<any> {
    const normalizedAction =
      action === 'approved' ? 'approve' :
      action === 'rejected' ? 'reject' :
      action === 'edited' ? 'edit' : action;

    return request<any>(`/api/v1/remediations/items/${itemId}/review`, {
      method: 'POST',
      body: JSON.stringify({
        action: normalizedAction,
        edited_question_text: edits?.edited_question_text,
        edited_answer_key: edits?.edited_answer_key || edits?.edited_expected_answer,
        review_notes: edits?.review_notes || edits?.edited_explanation,
      }),
    });
  },

  // Student Practice Sessions
  async startPracticeSession(submissionId: number): Promise<StudentPracticeSessionRead> {
    return request<StudentPracticeSessionRead>(
      `/api/v1/submissions/${submissionId}/practice-sessions?resume_active=true`,
      { method: 'POST' }
    );
  },

  async getPracticeSession(sessionId: number): Promise<StudentPracticeSessionRead> {
    return request<StudentPracticeSessionRead>(`/api/v1/practice-sessions/${sessionId}`);
  },

  async submitPracticeResponse(
    sessionId: number,
    remediationItemId: number,
    studentAnswer: string
  ): Promise<any> {
    return request<any>(`/api/v1/practice-sessions/${sessionId}/responses`, {
      method: 'POST',
      body: JSON.stringify({
        remediation_item_id: remediationItemId,
        student_answer: studentAnswer,
      }),
    });
  },

  async getPracticeSessionSummary(sessionId: number): Promise<PracticeSessionSummary> {
    return request<PracticeSessionSummary>(`/api/v1/practice-sessions/${sessionId}/summary`);
  },

  async completePracticeSession(sessionId: number): Promise<StudentPracticeSessionRead> {
    return request<StudentPracticeSessionRead>(`/api/v1/practice-sessions/${sessionId}/complete`, {
      method: 'POST',
    });
  },

  // Intervention Outcomes & Learning Loop Progress
  async getSubmissionInterventionOutcomes(submissionId: number): Promise<InterventionOutcomesSummary> {
    return request<InterventionOutcomesSummary>(`/api/v1/submissions/${submissionId}/intervention-outcomes`);
  },

  async getAssessmentInterventionOutcomes(assessmentId: number): Promise<InterventionOutcomesSummary> {
    return request<InterventionOutcomesSummary>(`/api/v1/assessments/${assessmentId}/intervention-outcomes`);
  },

  async getStudentProgressReport(submissionId: number): Promise<StudentProgressReport> {
    return request<StudentProgressReport>(`/api/v1/submissions/${submissionId}/student-progress`);
  },

  // Provider Status
  async getProvidersStatus(): Promise<{
    ocr_provider: string;
    ocr_real: boolean;
    evaluator_provider: string;
    evaluator_real: boolean;
    vllm_base_url?: string;
    vllm_model?: string;
    vllm_timeout_seconds?: number;
    vllm_reachable?: boolean;
    vllm_status_message?: string;
  }> {
    return request<any>('/api/v1/providers');
  },

  // AI Health Check
  async getAIHealth(): Promise<{
    status: 'online' | 'offline';
    provider: string;
    model?: string;
    error?: string;
  }> {
    return request<any>('/api/v1/health/ai');
  },

  // Demo Workflow Orchestration Helpers
  async ensureDemoContext(): Promise<{ submissionId: number; assessmentId: number }> {
    const assessmentsRes = await this.getAssessments(1, 10);
    let assessmentId: number;

    if (assessmentsRes.items && assessmentsRes.items.length > 0) {
      for (const a of assessmentsRes.items) {
        try {
          const subsRes = await this.getSubmissions(a.id);
          if (subsRes.items && subsRes.items.length > 0) {
            return { submissionId: subsRes.items[0].id, assessmentId: a.id };
          }
        } catch {
          // continue
        }
      }
      assessmentId = assessmentsRes.items[0].id;
    } else {
      const topic = await this.createTopic(
        'Calculus & Mechanics',
        'Foundational limits, derivatives, and Newtonian mechanics'
      );
      const assessment = await this.createAssessment(
        'Diagnostic Examination',
        'Evaluates calculus limits and laws of motion'
      );
      assessmentId = assessment.id;

      await this.createQuestion(assessmentId, {
        topic_id: topic.id,
        prompt: 'What is the derivative of f(x) = x^2?',
        question_type: 'short_answer',
        marks: 5.0,
        expected_answer: '2x',
      });
      await this.createQuestion(assessmentId, {
        topic_id: topic.id,
        prompt: "State Newton's second law of motion.",
        question_type: 'short_answer',
        marks: 5.0,
        expected_answer: 'F = ma',
      });
    }

    const subsRes = await this.getSubmissions(assessmentId);
    if (subsRes.items && subsRes.items.length > 0) {
      return { submissionId: subsRes.items[0].id, assessmentId };
    }

    const sub = await this.createSubmission(assessmentId);
    return { submissionId: sub.id, assessmentId };
  },

  async processDocumentEndToEnd(
    file: File,
    onStatusChange?: (statusText: string, step: number, progress?: ProcessingProgressInfo) => void,
    options?: {
      signal?: AbortSignal;
      maxWaitSeconds?: number;
      assessmentId?: number;
      answerSheetOnly?: boolean;
      difficulty?: 'Easy' | 'Medium' | 'Hard';
    }
  ): Promise<{
    upload: AnswerSheetUpload;
    extraction: OCRExtraction;
    proposals: ProposedAnswer[];
    evaluation: SubmissionEvaluationSummary;
    inferredQA?: InferredQAResponse;
    requiresManualReview?: boolean;
  }> {
    const notify = (statusText: string, step: number, prog?: Partial<ProcessingProgressInfo>) => {
      if (onStatusChange) {
        onStatusChange(statusText, step, {
          statusText,
          step,
          ...prog,
        });
      }
    };

    if (options?.signal?.aborted) {
      throw new Error('Processing cancelled by user.');
    }

    notify('Preparing submission context...', 1);
    let submissionId: number | undefined;
    if (options?.answerSheetOnly) {
      try {
        const zeroCtx = await this.createZeroQPContext(file.name);
        submissionId = zeroCtx.submission_id;
      } catch (err) {
        console.warn('Fallback to demo context for Zero-QP upload:', err);
        const demoCtx = await this.ensureDemoContext();
        submissionId = demoCtx.submissionId;
      }
    } else if (options?.assessmentId) {
      try {
        const subsRes = await this.getSubmissions(options.assessmentId);
        if (subsRes.items && subsRes.items.length > 0) {
          submissionId = subsRes.items[0].id;
        } else {
          // Attempt creation if caller is student or admin; for teacher this will gracefully fall back
          const sub = await this.createSubmission(options.assessmentId);
          submissionId = sub.id;
        }
      } catch {
        // Fallback to verified demo submission context
        const demoCtx = await this.ensureDemoContext();
        submissionId = demoCtx.submissionId;
      }
    } else {
      const demoCtx = await this.ensureDemoContext();
      submissionId = demoCtx.submissionId;
    }

    if (options?.signal?.aborted) {
      throw new Error('Processing cancelled by user.');
    }

    const isPdf = file.name.toLowerCase().endsWith('.pdf') || file.type === 'application/pdf';
    notify(`Uploading ${isPdf ? 'PDF document' : 'image answer sheet'}...`, 2);
    const upload = await this.uploadAnswerSheet(submissionId, file);

    if (options?.signal?.aborted) {
      throw new Error('Processing cancelled by user.');
    }

    notify('Triggering OCR extraction pipeline...', 3, { uploadId: upload.id });
    await this.triggerOCRProcess(upload.id);

    notify('Processing OCR in background...', 4, { uploadId: upload.id });
    // Default up to 600s (10 minutes) for large multi-page documents
    const maxAttempts = options?.maxWaitSeconds ? Math.ceil(options.maxWaitSeconds) : 600;
    const pollIntervalMs = 1000;
    let attempts = 0;
    let statusRes = await this.getOCRProcessingStatus(upload.id);

    while (
      attempts < maxAttempts &&
      !options?.signal?.aborted &&
      (statusRes.upload_status === 'uploaded' ||
        statusRes.upload_status === 'queued' ||
        statusRes.upload_status === 'processing')
    ) {
      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
      if (options?.signal?.aborted) {
        break;
      }
      statusRes = await this.getOCRProcessingStatus(upload.id);
      attempts++;

      const hasPageProgress = statusRes.total_pages && statusRes.total_pages > 0;
      const progressText = hasPageProgress
        ? `Processing page ${statusRes.pages_completed || 0} of ${statusRes.total_pages} (${statusRes.progress_percent || 0}%, ${attempts}s elapsed)...`
        : `Processing OCR in background (${attempts}s elapsed, status: ${statusRes.upload_status})...`;

      notify(progressText, 4, {
        uploadId: upload.id,
        pagesCompleted: statusRes.pages_completed,
        totalPages: statusRes.total_pages,
        progressPercent: statusRes.progress_percent,
      });
    }

    if (options?.signal?.aborted) {
      throw new Error(
        `Client polling was stopped by user. Document processing is continuing in the background on the server (Upload #${upload.id}).`
      );
    }

    // Terminal state checks:
    if (statusRes.upload_status === 'failed') {
      const errDetail = statusRes.latest_error_code
        ? `OCR processing failed with error code: ${statusRes.latest_error_code}`
        : 'OCR processing failed during execution.';
      throw new Error(errDetail);
    }

    if (
      statusRes.upload_status === 'uploaded' ||
      statusRes.upload_status === 'queued' ||
      statusRes.upload_status === 'processing'
    ) {
      const pageInfo = statusRes.total_pages
        ? ` (page ${statusRes.pages_completed || 0} of ${statusRes.total_pages})`
        : '';
      throw new Error(
        `OCR processing is still in progress on the server${pageInfo} after ${attempts}s. The server is continuing to process this document in the background.`
      );
    }

    if (
      (statusRes.upload_status === 'extracted' || statusRes.upload_status === 'needs_review') &&
      !statusRes.has_extraction
    ) {
      throw new Error(
        `OCR processing reached status '${statusRes.upload_status}', but extraction record is missing.`
      );
    }

    notify('Retrieving extracted text & structured segments...', 5, { uploadId: upload.id });
    const extraction = await this.getOCRExtraction(upload.id);

    if (options?.answerSheetOnly) {
      notify('Inferring questions & evaluating answers directly from student sheet...', 6, { uploadId: upload.id });
      const inferredQA = await this.inferQuestionsFromAnswerSheet(upload.id, options.difficulty);

      notify('Exam questions and diagnostic evaluations ready', 7, { uploadId: upload.id });

      const targetSubId = inferredQA.submission_id || submissionId;
      let evaluation: SubmissionEvaluationSummary = {
        submission_id: targetSubId,
        runs: [],
      };
      try {
        evaluation = await this.getSubmissionEvaluations(targetSubId);
      } catch {
        // fallback
      }

      let proposals: ProposedAnswer[] = [];
      try {
        const propRes = await this.getUploadProposedAnswers(upload.id);
        proposals = propRes.proposals || [];
      } catch {
        proposals = [];
      }

      notify('Complete', 8, { uploadId: upload.id });
      return {
        upload,
        extraction,
        proposals,
        evaluation,
        inferredQA,
        requiresManualReview: false,
      };
    }

    notify('Matching answer segments to questions...', 6, { uploadId: upload.id });
    let matchRes: AnswerMatchingResponse;
    try {
      matchRes = await this.matchUploadAnswers(upload.id);
    } catch {
      matchRes = await this.getUploadProposedAnswers(upload.id);
    }

    // Safeguard: OCR proposals are NEVER auto-approved based solely on OCR confidence.
    // Teacher review and explicit approval are strictly required before diagnostic evaluation.
    const hasMathOrQualityWarning = Boolean(
      extraction.has_math_content ||
      (extraction.quality_warnings && extraction.quality_warnings.length > 0)
    );
    const hasUnreviewedProposals = Boolean(
      matchRes.proposals && matchRes.proposals.some((p) => p.status === 'proposed' || p.status === 'needs_review' || p.status === 'unmatched')
    );
    const requiresManualReview = Boolean(hasMathOrQualityWarning || hasUnreviewedProposals);

    notify(
      hasMathOrQualityWarning
        ? 'OCR extraction complete (Teacher Review Required for Math/Layout Segments)'
        : 'OCR extraction complete (Teacher Review Required Before AI Evaluation)',
      7,
      { uploadId: upload.id }
    );

    // Do not auto-evaluate until the teacher has reviewed and approved answers
    let evaluation: SubmissionEvaluationSummary = {
      submission_id: submissionId,
      runs: [],
    };
    try {
      evaluation = await this.getSubmissionEvaluations(submissionId);
    } catch {
      // A new submission typically has no evaluations until teacher review
    }

    notify('Complete', 8, { uploadId: upload.id });
    return {
      upload,
      extraction,
      proposals: matchRes.proposals || [],
      evaluation,
      requiresManualReview,
    };
  },

  // Alias for backward compatibility
  async processPdfEndToEnd(
    file: File,
    onStatusChange?: (statusText: string, step: number, progress?: ProcessingProgressInfo) => void,
    options?: {
      signal?: AbortSignal;
      maxWaitSeconds?: number;
    }
  ) {
    return this.processDocumentEndToEnd(file, onStatusChange, options);
  },
};
