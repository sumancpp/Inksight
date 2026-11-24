export type UserRole = 'admin' | 'teacher' | 'student';

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit?: number;
  offset?: number;
  page?: number;
  size?: number;
  pages?: number;
}

export interface LearningTopic {
  id: number;
  name: string;
  description: string | null;
  parent_id?: number | null;
  created_at?: string;
  updated_at?: string;
}

export type QuestionType =
  | 'mcq'
  | 'multiple_choice'
  | 'short_answer'
  | 'numerical'
  | 'essay'
  | 'explain_reasoning';

export interface Question {
  id: number;
  assessment_id: number;
  topic_id: number;
  prompt: string;
  question_type: QuestionType;
  marks: number;
  expected_answer: string;
  rubric?: string | null;
  is_reference_proposed?: boolean;
  reference_status?: string;
  created_at?: string;
  updated_at?: string;
}

export interface Assessment {
  id: number;
  title: string;
  description: string | null;
  created_by: number;
  created_at?: string;
  updated_at?: string;
  questions?: Question[];
}

export type SubmissionStatus = 'draft' | 'submitted' | 'processing' | 'reviewed';

export interface Submission {
  id: number;
  assessment_id: number;
  student_id: number;
  status: SubmissionStatus;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface QuestionAnswer {
  id: number;
  submission_id: number;
  question_id: number;
  answer_text: string | null;
  awarded_marks: number | null;
  created_at: string;
  updated_at: string;
}

export type UploadStatus = 'uploaded' | 'queued' | 'processing' | 'extracted' | 'needs_review' | 'failed';

export interface AnswerSheetUpload {
  id: number;
  submission_id: number;
  original_filename: string;
  stored_filename: string;
  storage_path: string;
  content_type: string;
  file_size_bytes: number;
  upload_status: UploadStatus;
  uploaded_at: string;
}

export interface OCRProcessTriggerResponse {
  upload_id: number;
  status: UploadStatus;
  message: string;
}

export interface ProcessingStatusRead {
  upload_id: number;
  upload_status: UploadStatus;
  has_extraction: boolean;
  latest_error_code: string | null;
  updated_at: string;
  total_pages?: number | null;
  pages_completed?: number | null;
  progress_percent?: number | null;
}

export interface OCRExtraction {
  id: number;
  upload_id: number;
  extracted_text: string;
  structured_segments: any;
  confidence: number | null;
  provider_name: string;
  processing_status: string;
  error_code: string | null;
  created_at: string;
  updated_at: string;
  has_math_content?: boolean;
  quality_warnings?: string[] | null;
}

export type ProposalStatus =
  | 'proposed'
  | 'needs_review'
  | 'approved'
  | 'corrected'
  | 'rejected'
  | 'unmatched'
  | 'pending';

export interface ProposedAnswer {
  id: number;
  submission_id: number;
  upload_id: number;
  ocr_extraction_id: number;
  question_id?: number | null;
  segment_id?: number | null;
  proposed_text: string;
  corrected_text?: string | null;
  confidence?: number | null;
  confidence_score?: number;
  match_rationale?: string | null;
  rejection_reason?: string | null;
  reviewed_by?: number | null;
  reviewed_at?: string | null;
  review_notes?: string | null;
  status: ProposalStatus;
  created_at: string;
  updated_at: string;
}

export interface AnswerMatchingResponse {
  submission_id: number;
  upload_id: number | null;
  assessment_id?: number;
  total_questions?: number;
  matched_count: number;
  needs_review_count?: number;
  unmatched_count?: number;
  proposals: ProposedAnswer[];
  unmatched_segments?: any[];
  unanswered_questions?: any[];
  unmatched_segment_ids?: number[];
  unanswered_question_ids?: number[];
}

export type FindingReviewStatus =
  | 'pending_review'
  | 'accepted'
  | 'rejected'
  | 'needs_revision'
  | 'insufficient_evidence'
  | 'pending';

export interface MisconceptionItem {
  hypothesis: string;
  evidence_excerpt: string;
  linked_concept: string;
  severity?: 'low' | 'medium' | 'high' | null;
}

export interface ConfidenceDetails {
  score: number;
  level: 'low' | 'medium' | 'high';
  uncertainty_reasons: string[];
}

export interface TaskStatusResponse {
  task_id: string;
  status: 'PENDING' | 'STARTED' | 'SUCCESS' | 'FAILURE' | string;
  ready: boolean;
  successful?: boolean | null;
  result?: any;
  findings?: any[];
  error?: string | null;
}

export interface AsyncTaskAcceptedResponse {
  task_id: string;
  status: string;
  message: string;
  submission_id?: number;
}

export interface EvaluationFinding {
  id: number;
  run_id?: number;
  evaluation_run_id?: number;
  topic_id?: number | null;
  concept_name?: string | null;
  category: string;
  confidence: number;
  uncertainty_rationale?: string | null;
  evidence_excerpt?: string | null;
  rationale?: string;
  review_status: FindingReviewStatus;
  reviewed_by?: number | null;
  reviewed_at?: string | null;
  review_notes?: string | null;
  created_at: string;
  updated_at: string;
  // Evidence-driven Diagnostic Fields
  verdict?: string | null;
  correct_answer?: string | null;
  marks_awarded?: number | null;
  max_marks?: number | null;
  marks_reason?: string | null;
  error_amount?: string | null;
  error_type?: string | null;
  step_by_step_explanation?: string | null;
  misconception_hypothesis?: string | null;
  misconceptions?: MisconceptionItem[];
  confidence_details?: ConfidenceDetails | null;
  requires_teacher_review?: boolean;
  acknowledged_uncertainty?: boolean;
  teacher_corrected?: boolean;
  corrections?: FindingCorrection[];
  remediation_concept?: string | null;
  follow_up_question?: string | null;
  // Aliases for component convenience
  misconception_type?: string;
  confidence_score?: number;
  evidence_quote?: string | null;
  conceptual_explanation?: string | null;
  teacher_notes?: string | null;
}

export interface EvaluationRun {
  id: number;
  submission_id: number;
  question_id: number;
  evaluator_name: string;
  status?: 'pending' | 'completed' | 'failed' | string;
  error_message?: string | null;
  answer_text_snapshot: string;
  answer_text_hash?: string;
  is_cached?: boolean;
  findings: EvaluationFinding[];
  created_at: string;
  updated_at: string;
}

export interface SubmissionEvaluationSummary {
  submission_id: number;
  total_questions?: number;
  evaluated_count?: number;
  total_runs?: number;
  runs: EvaluationRun[];
}

export type RemediationReviewStatus = 'pending_review' | 'approved' | 'rejected' | 'edited';

export interface RemediationItemTeacherRead {
  id: number;
  run_id: number;
  finding_id: number;
  target_concept?: string | null;
  question_text: string;
  question_type: QuestionType | string;
  options: string[] | null;
  teacher_answer_key?: string | null;
  teacher_rationale?: string | null;
  difficulty?: string | null;
  uncertainty_note?: string | null;
  review_status: RemediationReviewStatus;
  edited_question_text?: string | null;
  edited_answer_key?: string | null;
  reviewed_by?: number | null;
  reviewed_at?: string | null;
  review_notes?: string | null;
  created_at: string;
  updated_at: string;
  effective_question_text?: string;
  effective_answer_key?: string | null;
  // Aliases for component convenience
  prompt?: string;
  expected_answer?: string;
  explanation?: string;
  edited_expected_answer?: string;
  edited_explanation?: string;
}

export interface RemediationRunDetailRead {
  id: number;
  finding_id: number;
  generator_name: string;
  items: RemediationItemTeacherRead[];
  created_at: string;
}

export type PracticeSessionStatus = 'active' | 'completed' | 'abandoned';

export interface StudentPracticeItemRead {
  id: number;
  finding_id?: number;
  target_concept?: string | null;
  question_text: string;
  question_type: QuestionType | string;
  options: string[] | null;
  difficulty?: string | null;
  answered?: boolean;
  // Compatibility alias
  prompt?: string;
}

export interface PracticeResponseRead {
  id: number;
  session_id: number;
  remediation_item_id: number;
  student_answer: string;
  score: number;
  is_correct: boolean;
  feedback: string | null;
  finding_id?: number;
  evaluation_run_id?: number;
  submitted_at: string;
}

export interface StudentPracticeSessionRead {
  id: number;
  student_id?: number;
  submission_id: number;
  status: PracticeSessionStatus;
  total_items?: number;
  completed_items?: number;
  created_at?: string;
  updated_at?: string;
  completed_at?: string | null;
  items: StudentPracticeItemRead[];
  responses: PracticeResponseRead[];
}

export interface ConceptPracticeProgress {
  concept_name: string;
  items_count: number;
  correct_count: number;
  evidence_summary: string;
}

export interface PracticeSessionSummary {
  session_id: number;
  submission_id: number;
  status: PracticeSessionStatus;
  total_items: number;
  completed_items: number;
  correct_count: number;
  total_score: number;
  max_score: number;
  accuracy_percentage: number;
  concepts_practiced: ConceptPracticeProgress[];
  pedagogical_disclaimer: string;
  // Aliases
  correct_items?: number;
  concept_breakdowns?: any[];
}

export interface StudentFollowupEvidence {
  item_id: number;
  question_type: string;
  student_answer: string;
  is_correct: boolean;
  score: number;
  feedback: string | null;
  submitted_at: string;
}

export interface StudentConceptProgress {
  topic_id?: number | null;
  topic_name?: string | null;
  concept_name: string;
  baseline_diagnostic_gap: string;
  baseline_evidence_excerpt?: string | null;
  evidence_count: number;
  correct_count: number;
  accuracy_percentage: number;
  outcome_status: 'improved' | 'uncertain' | 'persisting_gap' | 'pending_followup' | string;
  status_label: string;
  uncertainty_level: string;
  uncertainty_rationale: string;
  remaining_gaps?: string | null;
  recommended_next_step: string;
  followup_responses?: StudentFollowupEvidence[];
}

export interface StudentProgressReport {
  submission_id: number;
  assessment_id: number;
  assessment_title?: string | null;
  total_concepts_tracked: number;
  improved_count: number;
  uncertain_count: number;
  persisting_gap_count: number;
  pending_count: number;
  concepts: StudentConceptProgress[];
  overall_next_step: string;
  pedagogical_disclaimer: string;
}

export interface TeacherFollowupEvidence {
  response_id: number;
  session_id: number;
  remediation_item_id: number;
  item_question_text: string;
  item_question_type: string;
  difficulty?: string | null;
  student_answer: string;
  is_correct: boolean;
  score: number;
  feedback?: string | null;
  submitted_at: string;
}

export interface TeacherInterventionOutcome {
  finding_id: number;
  run_id: number;
  question_id: number;
  topic_id?: number | null;
  topic_name?: string | null;
  concept_name: string;
  student_id: number;
  student_name?: string | null;
  submission_id: number;
  prior_category: string;
  prior_confidence: number;
  prior_evidence_excerpt?: string | null;
  prior_rationale?: string | null;
  prior_uncertainty?: string | null;
  finding_review_status: string;
  finding_review_notes?: string | null;
  remediation_items_count: number;
  support_summary: string;
  evidence_count: number;
  correct_count: number;
  accuracy_percentage: number;
  latest_response_at?: string | null;
  followup_summary: string;
  followup_responses: TeacherFollowupEvidence[];
  outcome_status: 'improved' | 'uncertain' | 'persisting_gap' | 'pending_followup' | string;
  outcome_label: string;
  uncertainty_level: string;
  uncertainty_rationale: string;
  performance_comparison: string;
  recommended_action: string;
}

export interface InterventionOutcomesSummary {
  submission_id?: number | null;
  assessment_id?: number | null;
  total_interventions: number;
  improved_count: number;
  uncertain_count: number;
  persisting_gap_count: number;
  pending_count: number;
  outcomes: TeacherInterventionOutcome[];
  pedagogical_disclaimer: string;
}

export type FollowUpQuestionType = 'multiple_choice' | 'short_answer' | 'numerical' | 'step_based';
export type FollowUpStatus = 'proposed' | 'approved' | 'rejected';

export interface FollowUpRubricCriterion {
  text: string;
  marks: number;
}

export interface FollowUpRubric {
  criteria: FollowUpRubricCriterion[];
}

export interface FollowUpQuestion {
  id: number;
  finding_id: number;
  assessment_id: number;
  concept: string;
  question_text: string;
  expected_answer: string;
  rubric: FollowUpRubric;
  question_type: FollowUpQuestionType;
  status: FollowUpStatus;
  proposed_by: string;
  approved_by?: number | null;
  approved_at?: string | null;
  audit_notes?: string | null;
  created_at: string;
}

export type CorrectionFieldName =
  | 'misconception_hypothesis'
  | 'evidence_excerpt'
  | 'linked_concept'
  | 'severity'
  | 'confidence_score';

export type CorrectionStatus = 'active' | 'reverted';

export interface FindingCorrection {
  id: number;
  finding_id: number;
  field_name: CorrectionFieldName;
  original_value?: any;
  corrected_value: any;
  corrected_by?: number | null;
  corrected_at: string;
  correction_reason: string;
  status: CorrectionStatus;
}

export interface PendingReviewItem {
  finding_id: number;
  assessment_id: number;
  assessment_title?: string | null;
  submission_id: number;
  student_id: number;
  student_name: string;
  question_id: number;
  question_number?: number | null;
  question_prompt?: string | null;
  concept_name?: string | null;
  category: string;
  confidence: number;
  requires_teacher_review: boolean;
  acknowledged_uncertainty: boolean;
  review_status: string;
  teacher_corrected?: boolean;
  priority_score: number;
  priority_reasons: string[];
  brief_text?: string | null;
  misconceptions_count: number;
  created_at: string;
}

export interface PendingReviewQueueResponse {
  items: PendingReviewItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface MisconceptionClusterItem {
  cluster_id: string;
  linked_concept: string;
  hypothesis: string;
  student_count: number;
  student_ids: number[];
  finding_ids: number[];
  evidence_excerpts: string[];
  severity_distribution: Record<string, number>;
  recommended_intervention: string;
}

export interface MisconceptionClusterResponse {
  assessment_id: number;
  assessment_title?: string | null;
  clusters: MisconceptionClusterItem[];
  isolated: MisconceptionClusterItem[];
  total_findings_evaluated: number;
  total_students_evaluated: number;
}

export interface InferredQAItem {
  id?: number | null;
  question_number: number;
  inferred_question: string;
  student_answer: string;
  concept_name: string;
  expected_answer?: string | null;
  rubric?: string | null;
  verdict: 'correct' | 'partially_correct' | 'incorrect' | 'needs_teacher_review' | string;
  category: 'correct_understanding' | 'partially_correct_understanding' | 'likely_misconception' | 'insufficient_evidence' | string;
  marks_awarded: number;
  max_marks: number;
  step_by_step_explanation?: string | null;
  misconceptions: Array<Record<string, any>>;
  confidence: number;
  confidence_details?: Record<string, any> | null;
  requires_teacher_review: boolean;
  evidence_excerpt?: string | null;
  question_id?: number | null;
  finding_id?: number | null;
  proposal_id?: number | null;
}

export interface InferredQAUpdateRequest {
  inferred_question?: string;
  expected_answer?: string;
  re_evaluate?: boolean;
}

export interface InferredQAResponse {
  upload_id: number;
  submission_id: number;
  assessment_id: number;
  mode: string;
  total_inferred: number;
  items: InferredQAItem[];
  evaluation_summary?: Record<string, any> | null;
}



