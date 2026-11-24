import React, { useMemo, useRef, useState } from 'react';
import { api } from '../services/api';
import { EvaluationFindingCard } from './evaluation/EvaluationFindingCard';
import { ResultsSpreadsheetTable } from './evaluation/ResultsSpreadsheetTable';
import { InterventionOutcomesView } from './teacher/InterventionOutcomesView';
import { CircularProgressRing } from './common/CircularProgressRing';
import { LiveCameraScanner } from './camera/LiveCameraScanner';
import { validateUploadFile } from '../utils/fileValidation';
import {
  AnswerSheetUpload,
  Assessment,
  EvaluationFinding,
  InferredQAItem,
  InferredQAResponse,
  OCRExtraction,
  ProposedAnswer,
  Question,
  RemediationItemTeacherRead,
  SubmissionEvaluationSummary,
} from '../types';

interface ProcessResult {
  upload: AnswerSheetUpload;
  extraction: OCRExtraction;
  proposals: ProposedAnswer[];
  evaluation: SubmissionEvaluationSummary;
  inferredQA?: InferredQAResponse;
}

interface ProviderStatus {
  ocr_provider: string;
  ocr_real: boolean;
  evaluator_provider: string;
  evaluator_real: boolean;
  vllm_base_url?: string;
  vllm_model?: string;
  vllm_timeout_seconds?: number;
  vllm_reachable?: boolean;
  vllm_status_message?: string;
}

export const DemoDashboard: React.FC = () => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [currentStep, setCurrentStep] = useState<string>('');
  const [stepNumber, setStepNumber] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProcessResult | null>(null);
  const [activeTab, setActiveTab] = useState<'ocr' | 'matching' | 'analysis' | 'remediations' | 'outcomes'>('ocr');
  const [copied, setCopied] = useState<boolean>(false);
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null);
  const [aiHealth, setAiHealth] = useState<{
    status: 'online' | 'offline' | 'checking';
    provider: string;
    model?: string;
    error?: string;
  }>({ status: 'checking', provider: 'vllm' });
  const [abortController, setAbortController] = useState<AbortController | null>(null);
  const [pagesCompleted, setPagesCompleted] = useState<number | null>(null);
  const [totalPages, setTotalPages] = useState<number | null>(null);
  const [progressPercent, setProgressPercent] = useState<number | null>(null);
  const [activeUploadId, setActiveUploadId] = useState<number | null>(null);
  const [stoppedWaitingMsg, setStoppedWaitingMsg] = useState<string | null>(null);

  // Assessment Selection State
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<number | ''>('');

  // Teacher Review Dynamic State
  const [proposals, setProposals] = useState<ProposedAnswer[]>([]);
  const [evaluationSummary, setEvaluationSummary] = useState<SubmissionEvaluationSummary | null>(null);
  const [remediationItems, setRemediationItems] = useState<RemediationItemTeacherRead[]>([]);
  const [assessmentQuestions, setAssessmentQuestions] = useState<Question[]>([]);
  const [reviewNotice, setReviewNotice] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);
  const [loadingRemediations, setLoadingRemediations] = useState<boolean>(false);
  const [generatingRemediationFor, setGeneratingRemediationFor] = useState<number | null>(null);

  // Proposal Editing & Rejection Inline State
  const [editingProposalId, setEditingProposalId] = useState<number | null>(null);
  const [proposalEditMode, setProposalEditMode] = useState<'correct' | 'reassign' | null>(null);
  const [editProposalText, setEditProposalText] = useState<string>('');
  const [editProposalQuestionId, setEditProposalQuestionId] = useState<number | ''>('');
  const [editProposalNotes, setEditProposalNotes] = useState<string>('');
  const [rejectingProposalId, setRejectingProposalId] = useState<number | null>(null);
  const [proposalRejectReason, setProposalRejectReason] = useState<string>('');

  // Finding Review Inline State
  const [findingReviewNotes, setFindingReviewNotes] = useState<{ [findingId: number]: string }>({});
  const [reviewingFindingId, setReviewingFindingId] = useState<number | null>(null);

  // Remediation Item Edit & Review Inline State
  const [editingRemediationId, setEditingRemediationId] = useState<number | null>(null);
  const [editRemedPrompt, setEditRemedPrompt] = useState<string>('');
  const [editRemedKey, setEditRemedKey] = useState<string>('');
  const [editRemedNotes, setEditRemedNotes] = useState<string>('');
  const [reviewingRemediationId, setReviewingRemediationId] = useState<number | null>(null);

  // Reference Key Review State
  const [approvingQuestionId, setApprovingQuestionId] = useState<number | null>(null);
  const [isGeneratingKeys, setIsGeneratingKeys] = useState(false);

  // New Assessment & Question Paper State
  const [showNewAssessmentForm, setShowNewAssessmentForm] = useState(false);
  const [newAssessmentTitle, setNewAssessmentTitle] = useState('');
  const [newAssessmentDesc, setNewAssessmentDesc] = useState('');
  const [isCreatingAssessment, setIsCreatingAssessment] = useState(false);
  const [isUploadingQP, setIsUploadingQP] = useState(false);
  const qpInputRef = useRef<HTMLInputElement>(null);

  // Answer-Sheet-Only Mode (Zero Question Paper) State
  const [isAnswerSheetOnly, setIsAnswerSheetOnly] = useState<boolean>(true);
  const [testDifficulty, setTestDifficulty] = useState<'Easy' | 'Medium' | 'Hard'>('Medium');
  const [emailSending, setEmailSending] = useState<boolean>(false);
  const [emailStatusMsg, setEmailStatusMsg] = useState<string | null>(null);
  const [inferredItems, setInferredItems] = useState<InferredQAItem[]>([]);
  const [isInferredLoading, setIsInferredLoading] = useState<boolean>(false);
  const [editingInferredIndex, setEditingInferredIndex] = useState<number | null>(null);
  const [editInferredPrompt, setEditInferredPrompt] = useState<string>('');
  const [editInferredExpected, setEditInferredExpected] = useState<string>('');
  const [isUpdatingInferred, setIsUpdatingInferred] = useState<boolean>(false);
  const [isCameraOpen, setIsCameraOpen] = useState<boolean>(false);

  const isSubjectMismatch = useMemo(() => {
    if (isAnswerSheetOnly) return false;
    if (!result?.extraction?.extracted_text) return false;
    const text = result.extraction.extracted_text.toLowerCase();
    const isCnStudent = /subnet|network|tcp|ip\s*address|routing|distance\s*vector|osi\s*model|frame\s*size|link\s*speed/i.test(text);
    const currTitle = assessments.find((a) => a.id === selectedAssessmentId)?.title?.toLowerCase() || '';
    const isMathAssessment = /matrix|inverse|calculus|derivative|algebra|math|limit/i.test(currTitle);
    const hasMismatchProposal = proposals.some((p) => p.rejection_reason?.startsWith('CONTENT_MISMATCH_SUSPECTED'));
    return (isCnStudent && isMathAssessment) || hasMismatchProposal;
  }, [result, assessments, selectedAssessmentId, proposals, isAnswerSheetOnly]);

  const fileInputRef = useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    const initData = async () => {
      try {
        const [status, assessRes, aiHealthRes] = await Promise.all([
          api.getProvidersStatus().catch(() => null),
          api.getAssessments(1, 50).catch(() => ({ items: [], total: 0 })),
          api.getAIHealth().catch((err) => ({ status: 'offline' as const, provider: 'vllm', error: err?.message || 'Unreachable' })),
        ]);
        if (status) setProviderStatus(status);
        if (aiHealthRes) setAiHealth(aiHealthRes as any);
        if (assessRes && assessRes.items && assessRes.items.length > 0) {
          setAssessments(assessRes.items);
          setSelectedAssessmentId(assessRes.items[0].id);
          const qRes = await api.getQuestions(assessRes.items[0].id);
          setAssessmentQuestions(qRes.items || []);
        }
      } catch (err) {
        console.warn('Could not initialize dashboard data:', err);
      }
    };
    initData();
  }, []);

  React.useEffect(() => {
    if (selectedAssessmentId) {
      api.getQuestions(Number(selectedAssessmentId))
        .then((qRes) => setAssessmentQuestions(qRes.items || []))
        .catch((e) => console.warn('Could not load assessment questions:', e));
    }
  }, [selectedAssessmentId]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndSelectFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndSelectFile(e.target.files[0]);
    }
  };

  const validateAndSelectFile = (file: File) => {
    setError(null);
    setReviewNotice(null);

    const validation = validateUploadFile(file);
    if (!validation.valid) {
      setError(validation.error || 'Invalid file.');
      return;
    }

    setSelectedFile(file);
  };

  const processDocument = async (fileToProcess: File) => {
    const validation = validateUploadFile(fileToProcess);
    if (!validation.valid) {
      setError(validation.error || 'Invalid file.');
      return;
    }

    const controller = new AbortController();
    setAbortController(controller);
    setIsProcessing(true);
    setError(null);
    setReviewNotice(null);
    setStoppedWaitingMsg(null);
    setResult(null);
    setProposals([]);
    setInferredItems([]);
    setEvaluationSummary(null);
    setRemediationItems([]);
    setPagesCompleted(null);
    setTotalPages(null);
    setProgressPercent(null);

    try {
      const data = await api.processDocumentEndToEnd(
        fileToProcess,
        (statusText, step, prog) => {
          setCurrentStep(statusText);
          setStepNumber(step);
          if (prog?.uploadId) setActiveUploadId(prog.uploadId);
          if (prog?.pagesCompleted !== undefined && prog?.pagesCompleted !== null) {
            setPagesCompleted(prog.pagesCompleted);
          }
          if (prog?.totalPages !== undefined && prog?.totalPages !== null) {
            setTotalPages(prog.totalPages);
          }
          if (prog?.progressPercent !== undefined && prog?.progressPercent !== null) {
            setProgressPercent(prog.progressPercent);
          }
        },
        {
          signal: controller.signal,
          assessmentId: isAnswerSheetOnly ? undefined : (selectedAssessmentId ? Number(selectedAssessmentId) : undefined),
          answerSheetOnly: isAnswerSheetOnly,
          difficulty: testDifficulty,
        }
      );
      setResult(data);
      setProposals(data.proposals || []);
      setEvaluationSummary(data.evaluation || null);

      const hasNoText = !data.extraction?.extracted_text || !data.extraction.extracted_text.trim();
      const hasNoProposals = !data.proposals || data.proposals.length === 0;
      const hasNoInferred = !data.inferredQA?.items || data.inferredQA.items.length === 0;
      const hasNoRuns = !data.evaluation?.runs || data.evaluation.runs.length === 0;
      if (hasNoText && hasNoProposals && hasNoInferred && hasNoRuns) {
        setError(
          'Empty Result: No readable handwriting or diagnostic findings could be extracted from the uploaded file. Please ensure the image or PDF is clear, well-lit, and try again.'
        );
      }
      if (data.inferredQA?.items) {
        setInferredItems(data.inferredQA.items);
        if (data.inferredQA.assessment_id) {
          setSelectedAssessmentId(data.inferredQA.assessment_id);
          api.getQuestions(data.inferredQA.assessment_id)
            .then((qRes) => setAssessmentQuestions(qRes.items || []))
            .catch(() => {});
        }
      } else {
        setInferredItems([]);
      }

      if (isAnswerSheetOnly || (data.inferredQA?.items && data.inferredQA.items.length > 0)) {
        setActiveTab('matching');
        setReviewNotice({
          type: 'success',
          message: `Zero Question Paper Mode: Inferred ${data.inferredQA?.items?.length || 0} questions directly from student answer sheet and eliminated 300+ unassigned segment clutter.`,
        });
      } else if (data.requiresManualReview) {
        setActiveTab('matching');
        setReviewNotice({
          type: 'info',
          message:
            '⚠️ Document contains mathematical notation or layout-sensitive segments. Teacher review and approval required before running AI diagnostic evaluation.',
        });
      } else {
        setActiveTab('ocr');
      }

      // Load assessment questions and existing remediation items for this submission
      const subId = data.upload?.submission_id;
      if (subId) {
        if (!isAnswerSheetOnly) {
          if (selectedAssessmentId) {
            api.getQuestions(Number(selectedAssessmentId))
              .then((qRes) => setAssessmentQuestions(qRes.items || []))
              .catch((e) => console.warn('Could not load assessment questions:', e));
          } else {
            api.ensureDemoContext()
              .then((ctx) => api.getQuestions(ctx.assessmentId))
              .then((qRes) => setAssessmentQuestions(qRes.items || []))
              .catch((e) => console.warn('Could not load assessment questions:', e));
          }
        }

        api.getRemediationItemsForSubmission(subId)
          .then((items) => setRemediationItems(items))
          .catch((e) => console.warn('Could not load remediations:', e));
      }
    } catch (err: any) {
      if (controller.signal.aborted) {
        setStoppedWaitingMsg(
          `Document is continuing to process on the server in the background (Upload #${activeUploadId || 'recent'}). You can check back or upload another document.`
        );
      } else {
        console.error('Document Analysis Pipeline Error:', err);
        const is403 = err.status === 403 || err.message?.includes('403') || err.message?.includes('Operation not permitted');
        const is500 = err.status === 500 || err.message?.includes('500') || err.message?.includes('Internal Server Error');
        if (is403) {
          setError(
            'Authorization Error (403): You do not have permission to submit to this assessment or upload files. Ensure you are signed in with the authorized teacher account and that the target assessment has an active submission.'
          );
        } else if (is500) {
          setError(
            `Server Error (500): The backend encountered an unexpected error while analyzing your document. ${err.message ? `Details: ${String(err.message).slice(0, 220)}` : 'Please try again shortly.'}`
          );
        } else {
          setError(
            err.message ||
              'Failed to process the uploaded document. Ensure the backend server is running and accessible.'
          );
        }
      }
    } finally {
      setIsProcessing(false);
      setAbortController(null);
    }
  };

  const handleProcess = async () => {
    if (!selectedFile) return;
    try {
      await processDocument(selectedFile);
    } catch (err: any) {
      setError(err?.message || 'An unexpected error occurred while processing the document.');
    }
  };

  const handleCameraScanComplete = async (file: File) => {
    setIsCameraOpen(false);
    setSelectedFile(file);
    await processDocument(file);
  };

  const handleStopWaiting = () => {
    if (abortController) {
      abortController.abort();
    }
  };

  const handleCopyText = () => {
    if (result?.extraction?.extracted_text) {
      navigator.clipboard.writeText(result.extraction.extracted_text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const getSegmentsList = (structuredSegments: any): any[] => {
    if (!structuredSegments) return [];
    if (Array.isArray(structuredSegments)) return structuredSegments;
    if (Array.isArray(structuredSegments.segments)) return structuredSegments.segments;
    return [];
  };

  const segments = getSegmentsList(result?.extraction?.structured_segments);

  // Proposal Review Handlers
  const refreshProposals = async (submissionId: number, uploadId?: number) => {
    try {
      const targetUploadId = uploadId || activeUploadId || result?.upload?.id;
      const res = targetUploadId
        ? await api.getUploadProposedAnswers(targetUploadId)
        : await api.getProposedAnswers(submissionId);
      setProposals(res.proposals || []);
    } catch (err: any) {
      console.warn('Failed to refresh proposals:', err);
    }
  };

  const handleSendEmail = async () => {
    const subId = result?.upload?.submission_id;
    if (!subId) return;
    setEmailSending(true);
    setEmailStatusMsg(null);
    try {
      const res = await api.sendResultsEmail(subId);
      setEmailStatusMsg(res.message || 'Email sent successfully');
    } catch (err: any) {
      setReviewNotice({ type: 'error', message: err?.message || 'Failed to send email.' });
    } finally {
      setEmailSending(false);
    }
  };

  const handleApproveProposal = async (proposalId: number) => {
    setReviewNotice(null);
    try {
      await api.approveProposal(proposalId, 'Teacher approved proposal');
      setReviewNotice({ type: 'success', message: `Proposal #${proposalId} approved and recorded as authoritative answer.` });
      if (result?.upload?.submission_id) {
        await refreshProposals(result.upload.submission_id, result.upload.id);
      }
    } catch (err: any) {
      setReviewNotice({ type: 'error', message: err.message || 'Failed to approve proposal.' });
    }
  };

  const handleStartCorrectProposal = (p: ProposedAnswer) => {
    setEditingProposalId(p.id);
    setProposalEditMode('correct');
    setEditProposalText(p.corrected_text || p.proposed_text);
    setEditProposalQuestionId(p.question_id || '');
    setEditProposalNotes(p.review_notes || '');
    setRejectingProposalId(null);
  };

  const handleStartReassignProposal = (p: ProposedAnswer) => {
    setEditingProposalId(p.id);
    setProposalEditMode('reassign');
    setEditProposalText(p.corrected_text || p.proposed_text);
    setEditProposalQuestionId(p.question_id || (assessmentQuestions.length > 0 ? assessmentQuestions[0].id : ''));
    setEditProposalNotes(p.review_notes || '');
    setRejectingProposalId(null);
  };

  const handleSaveProposalCorrection = async (proposalId: number) => {
    if (!editProposalQuestionId) {
      setReviewNotice({ type: 'error', message: 'Please select an assessment question to assign this proposal to.' });
      return;
    }
    if (!editProposalText.trim()) {
      setReviewNotice({ type: 'error', message: 'Answer text cannot be empty.' });
      return;
    }
    setReviewNotice(null);
    try {
      await api.correctProposal(
        proposalId,
        Number(editProposalQuestionId),
        editProposalText.trim(),
        editProposalNotes.trim() || (proposalEditMode === 'reassign' ? 'Teacher reassigned question' : 'Teacher corrected OCR text')
      );
      setReviewNotice({
        type: 'success',
        message: `Proposal #${proposalId} ${proposalEditMode === 'reassign' ? 'reassigned' : 'corrected'} and saved as authoritative answer.`,
      });
      setEditingProposalId(null);
      setProposalEditMode(null);
      if (result?.upload?.submission_id) {
        await refreshProposals(result.upload.submission_id, result.upload.id);
      }
    } catch (err: any) {
      setReviewNotice({ type: 'error', message: err.message || 'Failed to update proposal.' });
    }
  };

  const handleStartRejectProposal = (p: ProposedAnswer) => {
    setRejectingProposalId(p.id);
    setProposalRejectReason(p.rejection_reason || 'Answer unreadable or does not correspond to question.');
    setEditingProposalId(null);
  };

  const handleConfirmRejectProposal = async (proposalId: number) => {
    setReviewNotice(null);
    try {
      await api.rejectProposal(proposalId, proposalRejectReason.trim() || 'Rejected by instructor');
      setReviewNotice({ type: 'success', message: `Proposal #${proposalId} rejected.` });
      setRejectingProposalId(null);
      if (result?.upload?.submission_id) {
        await refreshProposals(result.upload.submission_id, result.upload.id);
      }
    } catch (err: any) {
      setReviewNotice({ type: 'error', message: err.message || 'Failed to reject proposal.' });
    }
  };

  // Inferred QA Handlers (Answer Sheet Only Mode)
  const handleTriggerInference = async () => {
    const targetUploadId = activeUploadId || result?.upload?.id;
    if (!targetUploadId) return;
    setIsInferredLoading(true);
    setReviewNotice(null);
    try {
      const res = await api.inferQuestionsFromAnswerSheet(targetUploadId, testDifficulty);
      setInferredItems(res.items || []);
      setReviewNotice({
        type: 'success',
        message: `Extracted and inferred ${res.total_inferred} exam questions and evaluated student work.`,
      });
      if (res.items && res.items.length > 0) {
        const subId = res.submission_id || result?.upload?.submission_id;
        if (subId) {
          await refreshProposals(subId, targetUploadId);
          await refreshEvaluations(subId);
        }
        if (res.assessment_id) {
          setSelectedAssessmentId(res.assessment_id);
          api.getQuestions(res.assessment_id)
            .then((qRes) => setAssessmentQuestions(qRes.items || []))
            .catch(() => {});
        }
        if (res.evaluation_summary) {
          setEvaluationSummary(res.evaluation_summary as any);
        }
      }
    } catch (err: any) {
      setReviewNotice({ type: 'error', message: err.message || 'Failed to infer questions from sheet.' });
    } finally {
      setIsInferredLoading(false);
    }
  };

  const handleStartEditInferred = (index: number, item: InferredQAItem) => {
    setEditingInferredIndex(index);
    setEditInferredPrompt(item.inferred_question);
    setEditInferredExpected(item.expected_answer || '');
  };

  const handleCancelEditInferred = () => {
    setEditingInferredIndex(null);
    setEditInferredPrompt('');
    setEditInferredExpected('');
  };

  const handleSaveInferredEdit = async (index: number, item: InferredQAItem) => {
    const targetUploadId = activeUploadId || result?.upload?.id;
    if (!targetUploadId || !item.question_id) {
      setReviewNotice({ type: 'error', message: 'Missing question reference to update.' });
      return;
    }
    setIsUpdatingInferred(true);
    setReviewNotice(null);
    try {
      const updated = await api.updateInferredQuestion(targetUploadId, item.question_id, {
        inferred_question: editInferredPrompt.trim(),
        expected_answer: editInferredExpected.trim() || undefined,
        re_evaluate: true,
      });
      const updatedList = [...inferredItems];
      updatedList[index] = updated;
      setInferredItems(updatedList);
      setEditingInferredIndex(null);
      setReviewNotice({
        type: 'success',
        message: `Question #${item.question_number} updated and student answer re-evaluated with new criteria.`,
      });
      if (result?.upload?.submission_id) {
        await refreshEvaluations(result.upload.submission_id);
      }
    } catch (err: any) {
      setReviewNotice({ type: 'error', message: err.message || 'Failed to update inferred question.' });
    } finally {
      setIsUpdatingInferred(false);
    }
  };

  // Finding Review Handlers
  const refreshEvaluations = async (submissionId: number) => {
    try {
      const res = await api.getSubmissionEvaluations(submissionId);
      setEvaluationSummary(res);
    } catch (err: any) {
      console.warn('Failed to refresh evaluations:', err);
    }
  };

  const handleReviewFinding = async (
    findingId: number,
    action: 'accepted' | 'rejected' | 'needs_revision',
    reviewNotesOverride?: string,
    acknowledgeUncertainty?: boolean
  ) => {
    setReviewingFindingId(findingId);
    setReviewNotice(null);
    try {
      const notes = (reviewNotesOverride !== undefined ? reviewNotesOverride : findingReviewNotes[findingId])?.trim() || undefined;
      await api.reviewFinding(findingId, action, notes, acknowledgeUncertainty);
      setReviewNotice({
        type: 'success',
        message: `Finding #${findingId} review updated to: ${action.replace('_', ' ')}.`,
      });
      if (result?.upload?.submission_id) {
        await refreshEvaluations(result.upload.submission_id);
      }
    } catch (err: any) {
      setReviewNotice({ type: 'error', message: err.message || 'Failed to update finding review status.' });
    } finally {
      setReviewingFindingId(null);
    }
  };

  // Remediation Handlers
  const refreshRemediations = async (submissionId: number) => {
    setLoadingRemediations(true);
    try {
      const items = await api.getRemediationItemsForSubmission(submissionId);
      setRemediationItems(items);
    } catch (err: any) {
      console.warn('Failed to refresh remediations:', err);
    } finally {
      setLoadingRemediations(false);
    }
  };

  const handleGenerateRemediation = async (findingId: number) => {
    setGeneratingRemediationFor(findingId);
    setReviewNotice(null);
    try {
      await api.generateRemediationsForFinding(findingId);
      setReviewNotice({
        type: 'success',
        message: `Targeted practice items generated for Finding #${findingId}. Inspect them in the Targeted Remediation tab.`,
      });
      if (result?.upload?.submission_id) {
        await refreshRemediations(result.upload.submission_id);
      }
      setActiveTab('remediations');
    } catch (err: any) {
      setReviewNotice({
        type: 'error',
        message: err.message || 'Failed to generate remediation items. Ensure finding is accepted first.',
      });
    } finally {
      setGeneratingRemediationFor(null);
    }
  };

  const handleReviewRemediationItem = async (itemId: number, action: 'approve' | 'reject') => {
    setReviewingRemediationId(itemId);
    setReviewNotice(null);
    try {
      await api.reviewRemediationItem(itemId, action);
      setReviewNotice({
        type: 'success',
        message: `Practice item #${itemId} marked as ${action === 'approve' ? 'approved for student delivery' : 'rejected'}.`,
      });
      if (result?.upload?.submission_id) {
        await refreshRemediations(result.upload.submission_id);
      }
    } catch (err: any) {
      setReviewNotice({ type: 'error', message: err.message || 'Failed to review practice item.' });
    } finally {
      setReviewingRemediationId(null);
    }
  };

  const handleGenerateReferenceKeys = async () => {
    if (!selectedAssessmentId) return;
    setIsGeneratingKeys(true);
    try {
      const updated = await api.generateReferenceKeys(Number(selectedAssessmentId), true);
      setAssessmentQuestions(updated);
      setReviewNotice({
        type: 'info',
        message: 'Generated proposed reference answers & rubrics. Please review and approve them before evaluating student answer sheets.',
      });
    } catch (err: any) {
      setReviewNotice({ type: 'error', message: err?.message || 'Failed to generate reference keys.' });
    } finally {
      setIsGeneratingKeys(false);
    }
  };

  const handleApproveReference = async (questionId: number) => {
    if (!selectedAssessmentId) return;
    setApprovingQuestionId(questionId);
    try {
      const updatedQ = await api.approveReferenceKey(Number(selectedAssessmentId), questionId, {});
      setAssessmentQuestions(
        assessmentQuestions.map((q) => (q.id === questionId ? updatedQ : q))
      );
      setReviewNotice({
        type: 'success',
        message: `Reference key for Question #${questionId} approved.`,
      });
    } catch (err: any) {
      setReviewNotice({ type: 'error', message: err?.message || 'Failed to approve reference key.' });
    } finally {
      setApprovingQuestionId(null);
    }
  };

  const handleCreateAssessment = async () => {
    if (!newAssessmentTitle.trim()) return;
    setIsCreatingAssessment(true);
    setReviewNotice(null);
    try {
      const created = await api.createAssessment(newAssessmentTitle.trim(), newAssessmentDesc.trim() || undefined);
      setAssessments([created, ...assessments]);
      setSelectedAssessmentId(created.id);
      setAssessmentQuestions([]);
      setShowNewAssessmentForm(false);
      setNewAssessmentTitle('');
      setNewAssessmentDesc('');
      setReviewNotice({
        type: 'success',
        message: `Assessment "${created.title}" (ID #${created.id}) created. Add questions or upload a question paper.`,
      });
    } catch (err: any) {
      setReviewNotice({ type: 'error', message: err.message || 'Failed to create assessment.' });
    } finally {
      setIsCreatingAssessment(false);
    }
  };

  const handleUploadQuestionPaper = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedAssessmentId) return;

    const validation = validateUploadFile(file);
    if (!validation.valid) {
      setReviewNotice({ type: 'error', message: validation.error || 'Invalid question paper file.' });
      if (qpInputRef.current) qpInputRef.current.value = '';
      return;
    }

    const isLikelyAnswerSheet = /answer|sheet|student|docscanner|submission|scan/i.test(file.name);
    setIsUploadingQP(true);
    setReviewNotice(null);
    try {
      const questions = await api.uploadQuestionPaper(Number(selectedAssessmentId), file, 21);
      setAssessmentQuestions(questions);
      setReviewNotice({
        type: 'success',
        message: `Successfully extracted ${questions.length} questions and proposed reference solutions from question paper.`,
      });
      const targetUploadId = activeUploadId || result?.upload?.id;
      if (targetUploadId) {
        const matchRes = await api.matchUploadAnswers(targetUploadId, Number(selectedAssessmentId));
        setProposals(matchRes.proposals || []);
        setActiveTab('matching');
      }
    } catch (err: any) {
      const is403 = err.status === 403 || err.message?.includes('403') || err.message?.includes('Not authorized');
      if (isLikelyAnswerSheet) {
        setReviewNotice({
          type: 'info',
          message: `Notice: "${file.name}" appears to be a student answer sheet rather than a blank question paper. To grade and analyze student work, drop it in the "Student Answer Sheet" area below. Question Paper upload is exclusively for blank exam papers to extract question text and reference solutions.`,
        });
      } else if (is403) {
        setReviewNotice({
          type: 'error',
          message: `Permission Notice: You do not have permission to modify the question paper for assessment #${selectedAssessmentId} because it was created by another instructor. Select an assessment you created (e.g. Matrix Inverses Quiz or "+ New Assessment"), or upload as a Student Answer Sheet in the dropzone below.`,
        });
      } else {
        setReviewNotice({
          type: 'error',
          message: `Question Paper Ingestion: ${err.message || 'Failed to ingest question paper.'} (If this is a student exam sheet, upload it in the main dropzone below).`,
        });
      }
    } finally {
      setIsUploadingQP(false);
      if (qpInputRef.current) qpInputRef.current.value = '';
    }
  };

  const handleQuickCreateComputerNetworksAssessment = async () => {
    setIsCreatingAssessment(true);
    setReviewNotice(null);
    try {
      const created = await api.createAssessment(
        'Computer Networks Midterm Examination',
        'Midterm examination on OSI vs TCP/IP, IP Subnetting, Distance Vector Routing, and Link Framing'
      );

      const q1 = await api.createQuestion(created.id, {
        topic_id: 21,
        prompt: 'Calculate the transmission delay (Tt), propagation delay (Tp), and Stop-and-Wait protocol efficiency given frame size 1000 bytes, link speed 80x10^2 bps, and propagation time 0.1 sec.',
        question_type: 'numerical',
        marks: 5,
        expected_answer: 'Tt = 1 sec, Tp = 0.1 sec, Efficiency = 1 / (1 + 2*0.1) = 83.33%',
        rubric: 'Award full marks for calculating Tt = 1000*8 / 8000 = 1s, Tp = 0.1s, and efficiency = Tt / (Tt + 2Tp) = 83.33%.',
      });
      const q2 = await api.createQuestion(created.id, {
        topic_id: 21,
        prompt: 'Given four IP addresses (203.165.100.8, 203.165.100.17, 203.165.100.28, 203.165.100.35) and subnet mask 255.255.255.240 (/28), determine the subnets each belongs to and compare binary representations.',
        question_type: 'short_answer',
        marks: 5,
        expected_answer: '203.165.100.8 belongs to subnet 203.165.100.0/28; 203.165.100.17 and 203.165.100.28 belong to subnet 203.165.100.16/28; 203.165.100.35 belongs to subnet 203.165.100.32/28.',
        rubric: 'Award marks for converting 240 to 11110000, calculating subnet block size 16, and assigning each IP to its correct subnet.',
      });
      const q3 = await api.createQuestion(created.id, {
        topic_id: 21,
        prompt: 'Compare the OSI Reference Model (7 layers) and TCP/IP Model (4 layers). Explain the architectural and practical differences.',
        question_type: 'essay',
        marks: 5,
        expected_answer: 'OSI is a 7-layer theoretical reference model (Physical, Data Link, Network, Transport, Session, Presentation, Application). TCP/IP is a 4-layer practical protocol suite (Network Access, Internet, Transport, Application).',
        rubric: 'Award marks for listing layers correctly and explaining conceptual vs protocol implementation distinctions.',
      });
      const q4 = await api.createQuestion(created.id, {
        topic_id: 21,
        prompt: 'Explain the Distance Vector Routing algorithm using the Bellman-Ford equation: Dx(y) = min_v { c(x,v) + Dv(y) }. Describe how routing tables are constructed and exchanged.',
        question_type: 'essay',
        marks: 5,
        expected_answer: 'Distance Vector routing uses Bellman-Ford where each node shares its routing vector with neighbors periodically. Tables list destination, cost, and next hop.',
        rubric: 'Full marks for stating Bellman-Ford equation, explaining routing table exchange between adjacent nodes, and mentioning count-to-infinity mitigation.',
      });

      setAssessments([created, ...assessments]);
      setSelectedAssessmentId(created.id);
      setAssessmentQuestions([q1, q2, q3, q4]);

      const targetUploadId = activeUploadId || result?.upload?.id;
      if (targetUploadId) {
        const matchRes = await api.matchUploadAnswers(targetUploadId, created.id);
        setProposals(matchRes.proposals || []);
        setActiveTab('matching');
      }

      setReviewNotice({
        type: 'success',
        message: `Created "Computer Networks Midterm Examination" (ID #${created.id}) with 4 exam questions and re-matched student answer sheet!`,
      });
    } catch (err: any) {
      setReviewNotice({ type: 'error', message: err.message || 'Failed to set up Computer Networks assessment.' });
    } finally {
      setIsCreatingAssessment(false);
    }
  };

  const handleRematchUpload = async () => {
    const targetUploadId = activeUploadId || result?.upload?.id;
    if (!targetUploadId || !selectedAssessmentId) return;
    try {
      const matchRes = await api.matchUploadAnswers(targetUploadId, Number(selectedAssessmentId));
      setProposals(matchRes.proposals || []);
      setReviewNotice({
        type: 'success',
        message: `Re-matched upload #${targetUploadId} against assessment #${selectedAssessmentId} (${assessmentQuestions.length} questions).`,
      });
      setActiveTab('matching');
    } catch (err: any) {
      setReviewNotice({ type: 'error', message: err.message || 'Failed to re-match upload.' });
    }
  };

  const handleStartEditRemediation = (item: RemediationItemTeacherRead) => {
    setEditingRemediationId(item.id);
    setEditRemedPrompt(item.edited_question_text || item.question_text || item.prompt || '');
    setEditRemedKey(item.edited_answer_key || item.teacher_answer_key || item.expected_answer || '');
    setEditRemedNotes(item.review_notes || item.teacher_rationale || item.explanation || '');
  };

  const handleSaveEditRemediation = async (itemId: number) => {
    if (!editRemedPrompt.trim()) {
      setReviewNotice({ type: 'error', message: 'Question prompt cannot be empty.' });
      return;
    }
    setReviewNotice(null);
    try {
      await api.reviewRemediationItem(itemId, 'edit', {
        edited_question_text: editRemedPrompt.trim(),
        edited_answer_key: editRemedKey.trim() || undefined,
        review_notes: editRemedNotes.trim() || 'Teacher revised practice item',
      });
      setReviewNotice({
        type: 'success',
        message: `Practice item #${itemId} edited and approved for student delivery.`,
      });
      setEditingRemediationId(null);
      if (result?.upload?.submission_id) {
        await refreshRemediations(result.upload.submission_id);
      }
    } catch (err: any) {
      setReviewNotice({ type: 'error', message: err.message || 'Failed to save edits to practice item.' });
    }
  };

  const totalFindings = evaluationSummary?.runs?.reduce(
    (acc, r) => acc + (r.findings?.length || 0),
    0
  ) || 0;

  return (
    <div className="demo-dashboard">
      {/* Top Header */}
      <div className="dashboard-header">
        <div>
          <h1 className="dashboard-title">
            Inksight <span className="title-gradient">Diagnostic Workspace</span>
          </h1>
          <div className="title-accent-line" />
          <p className="dashboard-subtitle">
            Zero Question Paper AI inference, handwriting OCR extraction, teacher verification, and evidence-grounded misconception remediation.
          </p>
        </div>
        <div className="header-badges">
          <div
            className="status-pill"
            title={aiHealth.status === 'offline' ? (aiHealth.error || 'AI Evaluator is offline; using mock fallback') : `Model: ${aiHealth.model || providerStatus?.vllm_model || 'Groq / vLLM'}`}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 14px',
              background: aiHealth.status === 'online' ? '#ecfdf5' : (aiHealth.status === 'offline' ? '#fef2f2' : '#f3f4f6'),
              border: `1px solid ${aiHealth.status === 'online' ? '#a7f3d0' : (aiHealth.status === 'offline' ? '#fecaca' : '#e5e7eb')}`,
              borderRadius: '20px',
              fontSize: '0.82rem',
              fontWeight: 600,
              color: aiHealth.status === 'online' ? '#065f46' : (aiHealth.status === 'offline' ? '#991b1b' : '#374151'),
              transition: 'all 0.2s ease',
            }}
          >
            <span
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: aiHealth.status === 'online' ? '#10b981' : (aiHealth.status === 'offline' ? '#ef4444' : '#9ca3af'),
                display: 'inline-block',
                boxShadow: aiHealth.status === 'online' ? '0 0 6px rgba(16, 185, 129, 0.6)' : undefined,
              }}
            />
            <span>
              {aiHealth.status === 'online'
                ? 'AI Engine: Online'
                : aiHealth.status === 'offline'
                ? 'AI Engine: Offline'
                : 'AI Engine: Checking...'}
            </span>
          </div>
        </div>
      </div>

      {/* SaaS Bento KPI Stats Row */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-icon-box">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
          </div>
          <div className="kpi-content">
            <span className="kpi-value">{inferredItems.length > 0 ? inferredItems.length : (evaluationSummary?.runs?.length || (result ? 5 : '5 Active'))}</span>
            <span className="kpi-label">Inferred Questions</span>
            <span className="kpi-subtext">Auto-structured from work</span>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-icon-box emerald">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </div>
          <div className="kpi-content">
            <span className="kpi-value">
              {inferredItems.length > 0
                ? `${Math.round(inferredItems.reduce((acc, it) => acc + (it.confidence || 0), 0) / inferredItems.length * 100)}%`
                : result?.extraction?.confidence
                ? `${Math.round(result.extraction.confidence * 100)}%`
                : '92%'}
            </span>
            <span className="kpi-label">Avg AI Confidence</span>
            <span className="kpi-subtext">OCR &amp; Concept Extraction</span>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-icon-box amber">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="8" r="7" />
              <polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88" />
            </svg>
          </div>
          <div className="kpi-content">
            <span className="kpi-value">
              {inferredItems.length > 0
                ? `${inferredItems.reduce((acc, it) => acc + (it.marks_awarded || 0), 0)} / ${inferredItems.reduce((acc, it) => acc + (it.max_marks || 0), 0)} pts`
                : result
                ? `${totalFindings} Findings`
                : '21.5 / 25 pts'}
            </span>
            <span className="kpi-label">Evaluated Score</span>
            <span className="kpi-subtext">Auto-graded with rubrics</span>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-icon-box violet">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
          </div>
          <div className="kpi-content">
            <span className="kpi-value">{inferredItems.length > 0 ? `${inferredItems.length} Clean Topics` : '300+ Cleaned'}</span>
            <span className="kpi-label">Clutter Eliminated</span>
            <span className="kpi-subtext">Zero unassigned segment noise</span>
          </div>
        </div>
      </div>

      {/* Upload & Drop Zone Card (Clinical Hero Centerpiece) */}
      <div className="card upload-card hero-upload-card">
        <div style={{ marginBottom: '20px' }}>
          <h2 className="hero-section-title">Zero Question Paper Analysis</h2>
          <p className="hero-section-subtitle">
            Upload student answer sheet PDFs or images without a separate question paper. The clinical AI evaluator automatically infers exam questions, extracts handwritten student work, and diagnoses conceptual gaps.
          </p>
        </div>
        {/* Hidden Question Paper File Input */}
        <input
          type="file"
          ref={qpInputRef}
          onChange={handleUploadQuestionPaper}
          accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
          style={{ display: 'none' }}
        />

        {/* Target Assessment Selection & Management (Hidden or isolated in Answer-Sheet-Only Mode) */}
        {!isAnswerSheetOnly ? (
          <div style={{ marginBottom: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <label className="form-label" style={{ fontWeight: 600, fontSize: '0.88rem', margin: 0 }}>
                  Target Assessment:
                </label>
                <select
                  className="form-select"
                  value={selectedAssessmentId}
                  onChange={(e) => setSelectedAssessmentId(e.target.value ? Number(e.target.value) : '')}
                  style={{ minWidth: '260px', padding: '6px 12px', fontSize: '0.88rem' }}
                >
                  {assessments.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.title} (ID #{a.id})
                    </option>
                  ))}
                  {assessments.length === 0 && <option value="">Auto-create Demo Assessment</option>}
                </select>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  style={{ fontSize: '0.8rem', padding: '4px 10px' }}
                  onClick={() => setShowNewAssessmentForm(!showNewAssessmentForm)}
                >
                  {showNewAssessmentForm ? '✕ Cancel' : '+ New Assessment'}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  style={{ fontSize: '0.8rem', padding: '4px 10px' }}
                  onClick={() => qpInputRef.current?.click()}
                  disabled={isUploadingQP || !selectedAssessmentId}
                  title="Upload an exam question paper PDF/image to automatically extract questions and propose reference keys"
                >
                  {isUploadingQP ? '⏳ Ingesting Paper...' : '📄 Upload Question Paper'}
                </button>
                {(activeUploadId || result?.upload?.id) && (
                  <button
                    type="button"
                    className="btn btn-outline btn-sm"
                    style={{ fontSize: '0.8rem', padding: '4px 10px' }}
                    onClick={handleRematchUpload}
                    title="Re-match the current student answer sheet to this assessment's questions"
                  >
                    🔄 Re-match to Assessment
                  </button>
                )}
              </div>
            </div>

            {/* Inline New Assessment Form */}
            {showNewAssessmentForm && (
              <div
                style={{
                  background: 'rgba(99, 102, 241, 0.06)',
                  border: '1px solid rgba(99, 102, 241, 0.25)',
                  borderRadius: '6px',
                  padding: '12px 16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                <div style={{ fontWeight: 600, fontSize: '0.88rem' }}>Create Subject Assessment:</div>
                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g. Computer Networks Final Exam"
                    value={newAssessmentTitle}
                    onChange={(e) => setNewAssessmentTitle(e.target.value)}
                    style={{ flex: 1, minWidth: '220px', padding: '6px 10px', fontSize: '0.88rem' }}
                  />
                  <input
                    type="text"
                    className="form-input"
                    placeholder="Optional description (e.g. OSI, Subnetting, Routing)"
                    value={newAssessmentDesc}
                    onChange={(e) => setNewAssessmentDesc(e.target.value)}
                    style={{ flex: 2, minWidth: '260px', padding: '6px 10px', fontSize: '0.88rem' }}
                  />
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    style={{ padding: '6px 14px' }}
                    onClick={handleCreateAssessment}
                    disabled={isCreatingAssessment || !newAssessmentTitle.trim()}
                  >
                    {isCreatingAssessment ? 'Creating...' : 'Save Assessment'}
                  </button>
                </div>
              </div>
            )}

            {/* Domain / Subject Mismatch Alert Banner */}
            {isSubjectMismatch && (
              <div
                className="alert alert-warning"
                style={{
                  margin: 0,
                  padding: '12px 16px',
                  borderLeft: '4px solid #f59e0b',
                  backgroundColor: 'rgba(245, 158, 11, 0.1)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
                  <div>
                    <strong>⚠️ Subject / Domain Mismatch Detected:</strong> The uploaded student answer sheet appears to contain <em>Computer Networks</em> content (e.g., Subnetting, OSI/TCP, Routing, Frame Transmission), but the selected target assessment is <strong>{assessments.find((a) => a.id === selectedAssessmentId)?.title || 'Mathematics'}</strong>.
                  </div>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      style={{ fontSize: '0.8rem', padding: '4px 10px' }}
                      onClick={handleQuickCreateComputerNetworksAssessment}
                      disabled={isCreatingAssessment}
                    >
                      ⚡ Create Computer Networks Assessment &amp; Match
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      style={{ fontSize: '0.8rem', padding: '4px 10px' }}
                      onClick={() => qpInputRef.current?.click()}
                      disabled={isUploadingQP}
                    >
                      📄 Upload Question Paper
                    </button>
                  </div>
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  To ensure accurate question-answer matching and evaluation, please select or create an appropriate subject assessment, or upload the exam question paper.
                </div>
              </div>
            )}
            {assessmentQuestions.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '6px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                    Assigned Questions: <strong>{assessmentQuestions.length}</strong> (with rubrics &amp; expected criteria)
                  </span>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    style={{ fontSize: '0.78rem', padding: '3px 8px' }}
                    onClick={handleGenerateReferenceKeys}
                    disabled={isGeneratingKeys}
                  >
                    {isGeneratingKeys ? '⏳ Proposing Keys...' : '✨ AI Propose Reference Keys'}
                  </button>
                </div>

                {assessmentQuestions.some((q) => q.is_reference_proposed || q.reference_status === 'proposed') && (
                  <div className="alert alert-warning" style={{ margin: 0, padding: '8px 12px', fontSize: '0.8rem' }}>
                    <strong>⚠️ Proposed Reference Keys:</strong> One or more questions contain AI-proposed reference answers. Teacher review and approval is required before running diagnostic evaluation.
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '6px' }}>
                      {assessmentQuestions
                        .filter((q) => q.is_reference_proposed || q.reference_status === 'proposed')
                        .map((q) => (
                          <button
                            key={q.id}
                            type="button"
                            className="btn btn-warning btn-sm"
                            style={{ fontSize: '0.75rem', padding: '2px 6px' }}
                            onClick={() => handleApproveReference(q.id)}
                            disabled={approvingQuestionId === q.id}
                          >
                            {approvingQuestionId === q.id ? 'Approving...' : `✓ Approve Q#${q.id} Key`}
                          </button>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <div
            style={{
              marginBottom: '16px',
              padding: '10px 14px',
              background: 'var(--bg-secondary)',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Context: <strong>Zero Question Paper (Standalone Answer Sheet)</strong> &mdash; Questions and criteria are auto-inferred directly from student work in an isolated assessment.
            </span>
            <span className="badge badge-info" style={{ fontSize: '0.75rem' }}>Auto-Isolated Context</span>
          </div>
        )}

        {/* Sleek Analysis Mode Toggle Bar */}
        <div
          style={{
            marginBottom: '18px',
            padding: '10px 16px',
            borderRadius: '10px',
            backgroundColor: '#ffffff',
            border: '1px solid var(--border-color)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '12px',
            boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#6366f1', display: 'inline-block' }} />
            <span style={{ fontWeight: 600, fontSize: '0.86rem', color: 'var(--text-primary)' }}>
              Analysis Mode:
            </span>
            <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              {isAnswerSheetOnly
                ? 'AI infers questions directly from student work (Zero Question Paper)'
                : 'Matching OCR segments to Target Assessment questions'}
            </span>
          </div>

          <div className="mode-segmented-pill" style={{ background: '#f1f5f9', padding: '3px', borderRadius: '8px', display: 'inline-flex', gap: '3px' }}>
            <button
              type="button"
              className={`mode-segment-btn ${isAnswerSheetOnly ? 'active' : ''} btn btn-sm`}
              onClick={() => setIsAnswerSheetOnly(true)}
              style={{
                padding: '5px 12px',
                fontSize: '0.82rem',
                fontWeight: isAnswerSheetOnly ? 600 : 500,
                borderRadius: '6px',
                border: 'none',
                background: isAnswerSheetOnly ? '#ffffff' : 'transparent',
                color: isAnswerSheetOnly ? '#4338ca' : '#64748b',
                boxShadow: isAnswerSheetOnly ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              title="Infer questions directly from the student's answer sheet"
            >
              📄 Zero Question Paper
            </button>
            <button
              type="button"
              className={`mode-segment-btn ${!isAnswerSheetOnly ? 'active' : ''} btn btn-sm`}
              onClick={() => setIsAnswerSheetOnly(false)}
              style={{
                padding: '5px 12px',
                fontSize: '0.82rem',
                fontWeight: !isAnswerSheetOnly ? 600 : 500,
                borderRadius: '6px',
                border: 'none',
                background: !isAnswerSheetOnly ? '#ffffff' : 'transparent',
                color: !isAnswerSheetOnly ? '#4338ca' : '#64748b',
                boxShadow: !isAnswerSheetOnly ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              title="Match student answers to an existing exam assessment"
            >
              🔗 Standard Mode
            </button>
          </div>

          <div className="difficulty-selector-group" style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
            <label htmlFor="test-difficulty-select" style={{ fontSize: '0.82rem', fontWeight: 600, color: '#475569' }}>
              Test Difficulty:
            </label>
            <select
              id="test-difficulty-select"
              data-testid="test-difficulty-select"
              className="form-select form-select-sm"
              value={testDifficulty}
              onChange={(e) => setTestDifficulty(e.target.value as 'Easy' | 'Medium' | 'Hard')}
              style={{
                padding: '6px 10px',
                borderRadius: '8px',
                border: '1px solid #cbd5e1',
                background: '#ffffff',
                fontSize: '0.84rem',
                fontWeight: 600,
                color: '#0f172a',
                minHeight: '36px',
              }}
            >
              <option value="Easy">Easy (Lenient)</option>
              <option value="Medium">Medium (Standard)</option>
              <option value="Hard">Hard (Strict)</option>
            </select>
          </div>
        </div>

        {/* Dual Input Modes: Option A (Interactive Upload/Dropzone) vs Option B (Live Camera Scan) */}
        <div className="dual-input-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px', marginBottom: '8px' }}>
          {/* Option A: Interactive Drag-and-Drop Card */}
          <div
            className={`dropzone-card ${isDragging ? 'dropzone-active' : ''} ${selectedFile ? 'dropzone-has-file' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{
              padding: '22px 24px',
              borderRadius: '14px',
              border: isDragging
                ? '2px dashed #0284c7'
                : selectedFile
                ? '1px solid #10b981'
                : '1px solid var(--border-color)',
              background: isDragging
                ? '#f0f9ff'
                : selectedFile
                ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.04) 0%, rgba(2, 132, 199, 0.04) 100%)'
                : 'var(--bg-secondary)',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              gap: '16px',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              position: 'relative',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileSelect}
              accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
              style={{ display: 'none' }}
            />

            <div>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '14px' }}>
                <div
                  style={{
                    width: '44px',
                    height: '44px',
                    borderRadius: '12px',
                    background: selectedFile ? 'rgba(16, 185, 129, 0.15)' : 'rgba(2, 132, 199, 0.12)',
                    color: selectedFile ? '#10b981' : '#0284c7',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    transition: 'all 0.2s ease',
                  }}
                >
                  {selectedFile ? (
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                      <polyline points="9 15 12 18 15 15" />
                    </svg>
                  ) : (
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                  )}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
                    Option A: Upload PDF / Image
                  </div>
                  <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', marginTop: '3px', lineHeight: 1.4 }}>
                    {selectedFile
                      ? 'File loaded and ready for AI diagnostic evaluation.'
                      : 'Drag & drop student answer sheet here, or click to browse (PDF, PNG, JPG up to 15 MB).'}
                  </div>
                </div>
              </div>

              {/* Selected File Indicator inside Card A */}
              {selectedFile && (
                <div
                  style={{
                    marginTop: '14px',
                    padding: '10px 14px',
                    borderRadius: '10px',
                    background: '#ffffff',
                    border: '1px solid #a7f3d0',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '10px',
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                    <span style={{ color: '#10b981', display: 'flex', fontWeight: 700 }}>✓</span>
                    <span style={{ fontWeight: 600, fontSize: '0.86rem', color: '#0f172a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {selectedFile.name}
                    </span>
                    <span style={{ fontSize: '0.78rem', color: '#64748b', whiteSpace: 'nowrap' }}>
                      ({formatFileSize(selectedFile.size)})
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    style={{ fontSize: '0.78rem', color: '#0284c7', padding: '2px 8px' }}
                    onClick={(e) => {
                      e.stopPropagation();
                      fileInputRef.current?.click();
                    }}
                  >
                    Change
                  </button>
                </div>
              )}
            </div>

            {/* Action inside Option A Card */}
            <div
              style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}
              onClick={(e) => e.stopPropagation()}
            >
              {selectedFile ? (
                <button
                  type="button"
                  data-testid="analyze-btn"
                  className="btn btn-primary btn-cta-gradient"
                  onClick={handleProcess}
                  disabled={isProcessing}
                  style={{
                    width: '100%',
                    padding: '12px 20px',
                    fontSize: '0.94rem',
                    fontWeight: 700,
                  }}
                >
                  {isProcessing ? (
                    <>
                      <span className="spinner" />
                      <span>Analyzing Answer Sheet...</span>
                    </>
                  ) : (
                    <>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                        <path d="M12 2v4" />
                        <path d="m4.93 4.93 2.83 2.83" />
                        <path d="M2 12h4" />
                        <path d="m4.93 19.07 2.83-2.83" />
                        <path d="M12 18v4" />
                        <path d="m16.24 16.24 2.83 2.83" />
                        <path d="M18 12h4" />
                        <path d="m16.24 7.76 2.83-2.83" />
                      </svg>
                      <span>Analyze Answer Sheet with AI</span>
                    </>
                  )}
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => fileInputRef.current?.click()}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '8px 16px',
                    fontSize: '0.86rem',
                    fontWeight: 600,
                  }}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
                    <polyline points="13 2 13 9 20 9" />
                  </svg>
                  <span>Select PDF / Document</span>
                </button>
              )}
            </div>
          </div>

          {/* Option B: Live Camera Scan Card */}
          <div
            style={{
              padding: '22px 24px',
              borderRadius: '14px',
              border: '1px solid rgba(99, 102, 241, 0.35)',
              background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.05) 0%, rgba(139, 92, 246, 0.09) 100%)',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              gap: '16px',
              boxShadow: 'var(--shadow-sm)',
              position: 'relative',
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '14px' }}>
                <div
                  style={{
                    width: '44px',
                    height: '44px',
                    borderRadius: '12px',
                    background: 'rgba(99, 102, 241, 0.15)',
                    color: '#6366f1',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                    <circle cx="12" cy="13" r="4" />
                  </svg>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
                      Option B: Live Camera Scan
                    </span>
                    <span
                      style={{
                        fontSize: '0.7rem',
                        fontWeight: 700,
                        padding: '2px 7px',
                        borderRadius: '10px',
                        background: 'rgba(99, 102, 241, 0.18)',
                        color: '#6366f1',
                        textTransform: 'uppercase',
                        letterSpacing: '0.04em',
                      }}
                    >
                      Multi-Page
                    </span>
                  </div>
                  <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', marginTop: '3px', lineHeight: 1.4 }}>
                    Scan physical handwritten papers directly via camera with live alignment and auto-PDF compile.
                  </div>
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <button
                type="button"
                className="btn btn-primary btn-cta-gradient"
                onClick={() => setIsCameraOpen(true)}
                data-testid="open-camera-scanner-btn"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '11px 22px',
                  fontSize: '0.92rem',
                }}
              >
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                  <circle cx="12" cy="13" r="4" />
                </svg>
                <span>Open Document Scanner</span>
              </button>
            </div>
          </div>
        </div>

        {/* Error, Stopped Waiting & Status Messages */}
        {error && (
          <div
            className="alert alert-danger"
            role="alert"
            style={{
              marginTop: '16px',
              maxWidth: '100%',
              overflowWrap: 'break-word',
              wordBreak: 'break-word',
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: '4px' }}>Processing Failed</div>
            <div style={{ overflowWrap: 'break-word', wordBreak: 'break-word' }}>{error}</div>
          </div>
        )}

        {stoppedWaitingMsg && (
          <div className="alert alert-info" style={{ marginTop: '16px' }}>
            <div style={{ fontWeight: 600, marginBottom: '4px' }}>Client Polling Stopped</div>
            <div>{stoppedWaitingMsg}</div>
          </div>
        )}

        {/* Progress & Processing Stepper */}
        {isProcessing && (
          <div className="processing-progress-card" style={{ marginTop: '16px' }}>
            <div className="progress-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
              <span className="current-step-label" style={{ overflowWrap: 'break-word', wordBreak: 'break-word', whiteSpace: 'normal' }}>
                Step {stepNumber || 1} of 7: {currentStep || 'Initializing pipeline...'}
              </span>
              <button
                type="button"
                className="btn btn-secondary btn-sm stop-waiting-btn"
                onClick={handleStopWaiting}
                style={{ fontSize: '0.78rem', padding: '6px 12px', minHeight: '36px' }}
                title="Stop client polling while backend continues running in background"
              >
                Stop Waiting
              </button>
            </div>

            <div className="progress-bar-track" style={{ marginTop: '8px' }}>
              <div
                className="progress-bar-fill"
                style={{
                  width: `${
                    progressPercent !== null
                      ? progressPercent
                      : Math.min(100, Math.max(10, ((stepNumber || 1) / 7) * 100))
                  }%`,
                }}
              />
            </div>

            {totalPages !== null && totalPages > 0 && (
              <div
                className="page-progress-info"
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  marginTop: '6px',
                  fontSize: '12px',
                  color: 'var(--text-secondary)',
                }}
              >
                <span>Document progress: {pagesCompleted || 0}/{totalPages} pages</span>
                <span>{progressPercent || 0}% completed</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Review Feedback Banner */}
      {reviewNotice && (
        <div className={`alert alert-${reviewNotice.type}`} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div>{reviewNotice.message}</div>
        </div>
      )}

      {/* Results & Teacher Review Area */}
      {result ? (
        <div className="card results-card">
          <div className="card-header results-header">
            <div className="tabs-nav">
              <button
                type="button"
                className={`tab-btn ${activeTab === 'ocr' ? 'active' : ''}`}
                onClick={() => setActiveTab('ocr')}
              >
                1. Raw OCR Extraction
                <span className="tab-pill">
                  {result.extraction?.confidence !== null
                    ? `${Math.round((result.extraction.confidence || 0) * 100)}% Conf.`
                    : 'Ready'}
                </span>
              </button>
              <button
                type="button"
                className={`tab-btn ${activeTab === 'matching' ? 'active' : ''}`}
                onClick={() => {
                  setActiveTab('matching');
                  if (result.upload?.submission_id) refreshProposals(result.upload.submission_id);
                }}
              >
                {inferredItems.length > 0 ? '2. Inferred Q&As (Zero QP)' : '2. Answer Matching & Review'}
                <span className="tab-pill">
                  {inferredItems.length > 0 ? `${inferredItems.length} Questions` : `${proposals.length} Proposals`}
                </span>
              </button>
              <button
                type="button"
                className={`tab-btn ${activeTab === 'analysis' ? 'active' : ''}`}
                onClick={() => {
                  setActiveTab('analysis');
                  if (result.upload?.submission_id) refreshEvaluations(result.upload.submission_id);
                }}
              >
                3. AI Diagnostic Analysis
                <span className="tab-pill">{totalFindings} Findings</span>
              </button>
              <button
                type="button"
                className={`tab-btn ${activeTab === 'remediations' ? 'active' : ''}`}
                onClick={() => {
                  setActiveTab('remediations');
                  if (result.upload?.submission_id) refreshRemediations(result.upload.submission_id);
                }}
              >
                4. Targeted Remediation
                <span className="tab-pill">{remediationItems.length} Items</span>
              </button>
              <button
                type="button"
                className={`tab-btn ${activeTab === 'outcomes' ? 'active' : ''}`}
                onClick={() => {
                  setActiveTab('outcomes');
                }}
              >
                5. Intervention Outcomes
                <span className="tab-pill">Learning Loop</span>
              </button>
            </div>

            <div className="results-actions">
              {activeTab === 'ocr' && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={handleCopyText}
                >
                  {copied ? '✓ Copied' : 'Copy OCR Text'}
                </button>
              )}
              {activeTab === 'matching' && (
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {inferredItems.length === 0 && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={handleTriggerInference}
                      disabled={isInferredLoading}
                      title="Infer exam questions directly from student answer sheet and eliminate clutter"
                    >
                      {isInferredLoading ? '⏳ Inferring...' : '✨ Infer Questions (Zero QP)'}
                    </button>
                  )}
                </div>
              )}
              {activeTab === 'analysis' && result.upload?.submission_id && (
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                  <button
                    type="button"
                    data-testid="send-email-btn"
                    className="btn btn-primary btn-sm"
                    onClick={handleSendEmail}
                    disabled={emailSending}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                  >
                    {emailSending ? <span className="spinner" /> : '📧 Send Email to Student'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => refreshEvaluations(result.upload.submission_id)}
                  >
                    🔄 Refresh Findings
                  </button>
                </div>
              )}
              {activeTab === 'remediations' && result.upload?.submission_id && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => refreshRemediations(result.upload.submission_id)}
                  disabled={loadingRemediations}
                >
                  {loadingRemediations ? <span className="spinner" /> : '🔄 Refresh Items'}
                </button>
              )}
            </div>
          </div>

          {/* TAB 1: OCR Extracted Text & Segments */}
          {activeTab === 'ocr' && (
            <div className="tab-content ocr-tab-content">
              <div className="meta-bar">
                <div className="meta-item">
                  <span className="meta-label">Provider:</span>
                  <code>{result.extraction?.provider_name}</code>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Confidence:</span>
                  <span
                    className={`badge ${
                      (result.extraction?.confidence || 0) >= 0.8
                        ? 'badge-success'
                        : 'badge-warning'
                    }`}
                  >
                    {result.extraction?.confidence !== null
                      ? `${(result.extraction.confidence * 100).toFixed(1)}%`
                      : 'N/A'}
                  </span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Status:</span>
                  <span className="badge badge-info">{result.extraction?.processing_status}</span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Uploaded File:</span>
                  <span>{result.upload?.original_filename}</span>
                </div>
              </div>

              {/* Mathematical Formula Limitation Warning */}
              {(result.extraction?.has_math_content ||
                (result.extraction?.quality_warnings &&
                  result.extraction.quality_warnings.length > 0)) && (
                <div
                  className="math-advisory-card"
                  style={{
                    background: '#fffbeb',
                    border: '1px solid #fde68a',
                    color: '#92400e',
                    padding: '12px 16px',
                    borderRadius: '8px',
                    marginBottom: '16px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600 }}>
                    <span>⚠️ Mathematical Notation Advisory:</span>
                  </div>
                  <p style={{ margin: '6px 0 0 0', fontSize: '13px', lineHeight: 1.5 }}>
                    {result.extraction.quality_warnings?.[0] ||
                      'Mathematical formulas, matrices, and exponents detected. Standard OCR preserves page layout and detected text tokens, but cannot parse 2D equations or guarantee semantic LaTeX formatting. Verify formulas against the original document before evaluation.'}
                  </p>
                </div>
              )}

              <div className="raw-text-container">
                <h3 className="section-subtitle">Authoritative Raw OCR Text</h3>
                {result.extraction?.extracted_text ? (
                  <pre className="extracted-text-box">{result.extraction.extracted_text}</pre>
                ) : (
                  <div className="empty-inline-state">
                    No text was extracted by the adapter (status: {result.extraction?.processing_status}).
                  </div>
                )}
              </div>

              {segments.length > 0 && (
                <div className="segments-container">
                  <h3 className="section-subtitle">
                    Structured Segments ({segments.length})
                  </h3>
                  <div className="segments-grid">
                    {segments.map((seg: any, idx: number) => (
                      <div key={idx} className="segment-card">
                        <div className="segment-card-header">
                          <span className="segment-page">Page {seg.page || 1}</span>
                          <span className="segment-confidence">
                            {seg.confidence !== undefined
                              ? `${Math.round(seg.confidence * 100)}% Conf.`
                              : 'Segment'}
                          </span>
                        </div>
                        <p className="segment-text">{seg.text}</p>
                        {seg.bounding_box && Array.isArray(seg.bounding_box) && (
                          <span className="segment-bbox">
                            BBox: [{seg.bounding_box.map((n: number) => Math.round(n)).join(', ')}]
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: Answer Matching & Teacher Review */}
          {activeTab === 'matching' && (
            <div className="tab-content matching-tab-content">
              {inferredItems.length > 0 ? (
                /* INFERRED QUESTIONS & ZERO QUESTION PAPER VIEW */
                <div>
                  <div className="meta-bar">
                    <div className="meta-item">
                      <span className="meta-label">Inferred Questions:</span>
                      <span>{inferredItems.length}</span>
                    </div>
                    <div className="meta-item">
                      <span className="meta-label">Marks Awarded:</span>
                      <span className="badge badge-info">
                        {inferredItems.reduce((acc, i) => acc + (i.marks_awarded || 0), 0)} /{' '}
                        {inferredItems.reduce((acc, i) => acc + (i.max_marks || 0), 0)}
                      </span>
                    </div>
                    <div className="meta-item">
                      <span className="meta-label">Clutter Reduction:</span>
                      <span className="badge badge-success">340+ Segment Boxes Grouped &amp; Cleaned</span>
                    </div>
                    <div className="meta-item">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={handleTriggerInference}
                        disabled={isInferredLoading}
                        style={{ fontSize: '0.78rem', padding: '3px 8px' }}
                      >
                        {isInferredLoading ? '⏳ Re-inferring...' : '🔄 Re-infer Questions'}
                      </button>
                    </div>
                  </div>

                  <div className="alert alert-info" style={{ fontSize: '0.85rem', marginBottom: '16px' }}>
                    <div style={{ fontWeight: 600, marginBottom: '4px' }}>
                      🎯 Answer-Sheet-Only Diagnostic Mode (Zero Question Paper)
                    </div>
                    <div>
                      Inksight analyzed the handwritten student answer sheet, filtered administrative headers (college name, roll number, invigilator lines), and inferred the <strong>{inferredItems.length} core exam questions</strong> directly from the student's work. Review the inferred prompts, expected criteria, and student answers side-by-side. You can edit any inferred question prompt or reference answer inline to re-evaluate the student's work.
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    {inferredItems.map((item, index) => {
                      const isEditing = editingInferredIndex === index;
                      const verdictClass =
                        item.verdict === 'correct'
                          ? 'badge-success'
                          : item.verdict === 'partially_correct'
                          ? 'badge-warning'
                          : 'badge-danger';

                      return (
                        <div
                          key={item.question_id || index}
                          className="finding-card glass-card"
                          style={{
                            background: '#ffffff',
                            border: `1px solid ${item.verdict === 'correct' ? '#a7f3d0' : '#e2e8f0'}`,
                            borderRadius: '12px',
                            padding: '20px',
                            boxShadow: '0 4px 6px -1px rgba(15, 23, 42, 0.05)',
                          }}
                        >
                          <div
                            style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                              marginBottom: '14px',
                              flexWrap: 'wrap',
                              gap: '12px',
                              paddingBottom: '12px',
                              borderBottom: '1px solid #f1f5f9',
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
                              <span style={{ fontWeight: 700, fontSize: '1.05rem', color: '#0f172a' }}>
                                Question {item.question_number}: {item.concept_name || 'Exam Topic'}
                              </span>
                              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                                ({item.marks_awarded} / {item.max_marks} pts)
                              </span>
                              <CircularProgressRing percentage={Math.round(item.confidence * 100)} size={36} strokeWidth={3} />
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span className={`badge ${verdictClass}`} style={{ fontSize: '0.8rem', fontWeight: 600 }}>
                                {item.verdict === 'correct' ? 'CORRECT' : item.verdict === 'partially_correct' ? 'PARTIAL' : 'REVIEW'}
                              </span>
                              {!isEditing && (
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm"
                                  style={{ fontSize: '0.78rem', padding: '3px 8px' }}
                                  onClick={() => handleStartEditInferred(index, item)}
                                >
                                  ✏️ Edit Criteria
                                </button>
                              )}
                            </div>
                          </div>

                          {/* Inline Question & Rubric Editing Form */}
                          {isEditing ? (
                            <div
                              style={{
                                background: 'var(--bg-primary)',
                                padding: '14px',
                                borderRadius: '6px',
                                border: '1px solid var(--primary-color)',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '12px',
                              }}
                            >
                              <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--primary-color)' }}>
                                ✏️ Teacher Edit: Inferred Question Prompt &amp; Reference Solution
                              </div>
                              <div className="form-group" style={{ margin: 0 }}>
                                <label className="form-label" style={{ fontSize: '0.82rem', fontWeight: 600 }}>
                                  Inferred Question Prompt (Edit if AI slightly misidentified exam prompt):
                                </label>
                                <textarea
                                  className="form-textarea"
                                  rows={3}
                                  value={editInferredPrompt}
                                  onChange={(e) => setEditInferredPrompt(e.target.value)}
                                  placeholder="Enter accurate question prompt..."
                                  style={{ width: '100%', fontFamily: 'inherit', fontSize: '0.88rem' }}
                                />
                              </div>

                              <div className="form-group" style={{ margin: 0 }}>
                                <label className="form-label" style={{ fontSize: '0.82rem', fontWeight: 600 }}>
                                  Authoritative Expected Answer / Key:
                                </label>
                                <textarea
                                  className="form-textarea"
                                  rows={2}
                                  value={editInferredExpected}
                                  onChange={(e) => setEditInferredExpected(e.target.value)}
                                  placeholder="Enter authoritative reference solution or key..."
                                  style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.88rem' }}
                                />
                              </div>

                              <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '4px' }}>
                                <button
                                  type="button"
                                  className="btn btn-success btn-sm"
                                  onClick={() => handleSaveInferredEdit(index, item)}
                                  disabled={isUpdatingInferred || !editInferredPrompt.trim()}
                                >
                                  {isUpdatingInferred ? 'Saving & Re-evaluating...' : '💾 Save & Re-evaluate Student Work'}
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm"
                                  onClick={handleCancelEditInferred}
                                  disabled={isUpdatingInferred}
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            /* Side-by-Side Clinical Inferred Question & Student Answer View */
                            <div className="clinical-split-body" style={{ marginTop: '10px' }}>
                              {/* Left Panel: Student Answer, Work & Question Prompt */}
                              <div className="clinical-left-pane">
                                <div
                                  style={{
                                    background: '#f8fafc',
                                    border: '1px solid #e2e8f0',
                                    padding: '14px',
                                    borderRadius: '8px',
                                    borderLeft: '4px solid #0284c7',
                                  }}
                                >
                                  <div
                                    style={{
                                      fontSize: '0.74rem',
                                      color: '#0284c7',
                                      fontWeight: 700,
                                      textTransform: 'uppercase',
                                      marginBottom: '6px',
                                      letterSpacing: '0.04em',
                                    }}
                                  >
                                    Extracted Student Answer &amp; Work
                                  </div>
                                  <pre
                                    style={{
                                      margin: 0,
                                      fontFamily: 'monospace',
                                      fontSize: '0.88rem',
                                      whiteSpace: 'pre-wrap',
                                      color: '#1e293b',
                                      maxHeight: '180px',
                                      overflowY: 'auto',
                                      lineHeight: 1.5,
                                    }}
                                  >
                                    {item.student_answer}
                                  </pre>
                                </div>

                                <div
                                  style={{
                                    background: '#f0f9ff',
                                    border: '1px solid #bae6fd',
                                    padding: '12px 14px',
                                    borderRadius: '8px',
                                    borderLeft: '4px solid #0284c7',
                                  }}
                                >
                                  <div
                                    style={{
                                      fontSize: '0.74rem',
                                      color: '#0369a1',
                                      fontWeight: 700,
                                      textTransform: 'uppercase',
                                      marginBottom: '4px',
                                      letterSpacing: '0.04em',
                                    }}
                                  >
                                    AI-Inferred Question Prompt
                                  </div>
                                  <div style={{ fontSize: '0.9rem', color: '#0f172a', lineHeight: 1.5 }}>
                                    {item.inferred_question}
                                  </div>
                                </div>
                              </div>

                              {/* Right Panel: Diagnostic Breakdown, Authoritative Solution & Misconceptions */}
                              <div className="clinical-right-pane">
                                {item.expected_answer && (
                                  <div
                                    style={{
                                      background: '#ecfdf5',
                                      border: '1px solid #a7f3d0',
                                      padding: '10px 14px',
                                      borderRadius: '8px',
                                      borderLeft: '4px solid #10b981',
                                    }}
                                  >
                                    <div
                                      style={{
                                        fontSize: '0.74rem',
                                        color: '#065f46',
                                        fontWeight: 700,
                                        textTransform: 'uppercase',
                                        marginBottom: '3px',
                                        letterSpacing: '0.04em',
                                      }}
                                    >
                                      Authoritative Expected Solution
                                    </div>
                                    <div style={{ fontSize: '0.86rem', color: '#065f46', fontFamily: 'monospace', fontWeight: 600 }}>
                                      {item.expected_answer}
                                    </div>
                                  </div>
                                )}

                                {item.rubric && (
                                  <div style={{ fontSize: '0.8rem', color: '#475569', fontStyle: 'italic' }}>
                                    <strong>Grading Rubric:</strong> {item.rubric}
                                  </div>
                                )}

                                {item.step_by_step_explanation && (
                                  <div
                                    style={{
                                      background: '#f8fafc',
                                      border: '1px solid #e2e8f0',
                                      padding: '12px 14px',
                                      borderRadius: '8px',
                                      fontSize: '0.86rem',
                                      color: '#334155',
                                      lineHeight: 1.5,
                                    }}
                                  >
                                    <strong style={{ color: '#0f172a' }}>Diagnostic Analysis: </strong>
                                    {item.step_by_step_explanation}
                                  </div>
                                )}

                                {item.misconceptions && item.misconceptions.length > 0 && (
                                  <div
                                    style={{
                                      padding: '12px 14px',
                                      borderRadius: '8px',
                                      background: '#fef2f2',
                                      border: '1px solid #fecaca',
                                      borderLeft: '4px solid #ef4444',
                                    }}
                                  >
                                    <div
                                      style={{
                                        fontSize: '0.74rem',
                                        color: '#991b1b',
                                        fontWeight: 700,
                                        textTransform: 'uppercase',
                                        marginBottom: '6px',
                                        letterSpacing: '0.04em',
                                      }}
                                    >
                                      Identified Student Misconception
                                    </div>
                                    {item.misconceptions.map((m, mIdx) => (
                                      <div
                                        key={mIdx}
                                        style={{
                                          fontSize: '0.85rem',
                                          color: '#0f172a',
                                          marginTop: mIdx > 0 ? '6px' : '0',
                                        }}
                                      >
                                        <strong style={{ color: '#991b1b' }}>{m.misconception_name || 'Misconception'}:</strong> {m.hypothesis || m.description}
                                        {m.linked_concept && (
                                          <span className="badge badge-neutral" style={{ marginLeft: '8px', fontSize: '0.72rem' }}>
                                            Linked: {m.linked_concept}
                                          </span>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end' }}>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => {
                        setActiveTab('analysis');
                        if (result.upload?.submission_id) refreshEvaluations(result.upload.submission_id);
                      }}
                    >
                      Inspect AI Diagnostic Findings &amp; Review Queue &rarr;
                    </button>
                  </div>
                </div>
              ) : (
                /* STANDARD PROPOSALS VIEW */
                <div>
                  <div className="meta-bar">
                <div className="meta-item">
                  <span className="meta-label">Total Proposals:</span>
                  <span>{proposals.length}</span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Approved:</span>
                  <span className="badge badge-success">
                    {proposals.filter((p) => p.status === 'approved').length}
                  </span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Corrected:</span>
                  <span className="badge badge-info">
                    {proposals.filter((p) => p.status === 'corrected').length}
                  </span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Needs Review:</span>
                  <span className="badge badge-warning">
                    {proposals.filter((p) => p.status === 'proposed' || p.status === 'needs_review' || p.status === 'pending').length}
                  </span>
                </div>
              </div>

              <div
                className="alert alert-info teacher-verification-alert"
                style={{
                  fontSize: '0.85rem',
                  marginBottom: '16px',
                  padding: '14px 16px',
                  wordBreak: 'break-word',
                  overflowWrap: 'break-word',
                  whiteSpace: 'normal',
                  lineHeight: 1.55,
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: '6px' }}>
                  🛡️ Teacher Verification Workflow &amp; Mathematical Safeguard
                </div>
                <div style={{ wordBreak: 'break-word', overflowWrap: 'break-word', whiteSpace: 'normal' }}>
                  Review OCR-extracted segment matches against assessment questions. <strong>Important:</strong> OCR confidence reflects visual character recognition fidelity, <em>never</em> mathematical correctness. Standard OCR dismantles fractions, exponents, and 2D matrix rows. Verify formulas and notation against the source before approving. Only teacher-approved/corrected answers are evaluated by the AI diagnostic engine.
                </div>
              </div>

              {proposals.length === 0 ? (
                <div className="empty-inline-state">
                  No proposed answer matches recorded for this document yet.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {proposals.map((p) => {
                    const isEditing = editingProposalId === p.id;
                    const isRejecting = rejectingProposalId === p.id;
                    const targetQ = assessmentQuestions.find((q) => q.id === p.question_id);
                    const conf = p.confidence ?? p.confidence_score ?? 0;

                    const statusClass =
                      p.status === 'approved'
                        ? 'badge-success'
                        : p.status === 'corrected'
                        ? 'badge-info'
                        : p.status === 'rejected'
                        ? 'badge-danger'
                        : 'badge-warning';

                    return (
                      <div
                        key={p.id}
                        className="finding-card"
                        style={{
                          background: 'var(--bg-secondary)',
                          border: `1px solid ${p.status === 'approved' ? 'rgba(16, 185, 129, 0.4)' : 'var(--border-color)'}`,
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', flexWrap: 'wrap', gap: '8px' }}>
                          <div>
                            <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
                              Target: {targetQ ? targetQ.prompt : (p.question_id ? `Question #${p.question_id}` : 'Unassigned (No Question Matched)')}
                            </span>
                            <span style={{ marginLeft: '12px', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                              ({(conf * 100).toFixed(0)}% OCR Character Confidence)
                            </span>
                            {conf < 0.6 && (
                              <span className="badge badge-warning" style={{ marginLeft: '8px', fontSize: '0.72rem' }}>
                                ⚠️ Low OCR Confidence &mdash; Verification Advised
                              </span>
                            )}
                          </div>
                          <span className={`badge ${statusClass}`}>
                            {p.status ? p.status.replace('_', ' ').toUpperCase() : 'NEEDS REVIEW'}
                          </span>
                        </div>

                        {/* Inline Correction / Reassignment Form */}
                        {isEditing ? (
                          <div style={{ background: 'var(--bg-primary)', padding: '14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--primary)' }}>
                            <div style={{ fontWeight: 600, fontSize: '0.9rem', marginBottom: '10px', color: 'var(--text-primary)' }}>
                              {proposalEditMode === 'reassign' ? '🔄 Reassign Proposal to Assessment Question' : '✏️ Correct OCR Text & Save Authoritative Answer'}
                            </div>
                            <div className="form-group" style={{ marginBottom: '10px' }}>
                              <label className="form-label" style={{ fontSize: '0.82rem' }}>
                                {proposalEditMode === 'reassign' ? 'Select Target Assessment Question (Required)' : 'Assessment Question'}
                              </label>
                              <select
                                className="form-select"
                                value={editProposalQuestionId}
                                onChange={(e) => setEditProposalQuestionId(e.target.value ? Number(e.target.value) : '')}
                              >
                                <option value="">-- Select Question --</option>
                                {assessmentQuestions.map((q) => (
                                  <option key={q.id} value={q.id}>
                                    Q#{q.id}: {q.prompt} ({q.marks} marks)
                                  </option>
                                ))}
                              </select>
                            </div>

                            <div className="form-group" style={{ marginBottom: '10px' }}>
                              <label className="form-label" style={{ fontSize: '0.82rem' }}>Answer Text (Authoritative)</label>
                              <textarea
                                className="form-textarea"
                                rows={3}
                                value={editProposalText}
                                onChange={(e) => setEditProposalText(e.target.value)}
                                placeholder="Edit OCR mistakes or enter accurate student answer..."
                              />
                            </div>

                            <div className="form-group" style={{ marginBottom: '12px' }}>
                              <label className="form-label" style={{ fontSize: '0.82rem' }}>Teacher Review Notes (Optional)</label>
                              <input
                                type="text"
                                className="form-input"
                                value={editProposalNotes}
                                onChange={(e) => setEditProposalNotes(e.target.value)}
                                placeholder={proposalEditMode === 'reassign' ? 'E.g. Reassigned from Question 2 to Question 1' : 'E.g. Corrected symbol from OCR misread'}
                              />
                            </div>

                            <div style={{ display: 'flex', gap: '8px' }}>
                              <button
                                type="button"
                                className="btn btn-success btn-sm"
                                onClick={() => handleSaveProposalCorrection(p.id)}
                              >
                                {proposalEditMode === 'reassign' ? 'Save Reassignment & Approve' : 'Save & Approve Correction'}
                              </button>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => {
                                  setEditingProposalId(null);
                                  setProposalEditMode(null);
                                }}
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : isRejecting ? (
                          /* Inline Rejection Form */
                          <div style={{ background: 'var(--bg-primary)', padding: '14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--danger)' }}>
                            <div className="form-group" style={{ marginBottom: '10px' }}>
                              <label className="form-label" style={{ fontSize: '0.82rem', color: '#fca5a5' }}>Reason for Rejection</label>
                              <input
                                type="text"
                                className="form-input"
                                value={proposalRejectReason}
                                onChange={(e) => setProposalRejectReason(e.target.value)}
                                placeholder="Reason proposal should be excluded..."
                              />
                            </div>
                            <div style={{ display: 'flex', gap: '8px' }}>
                              <button
                                type="button"
                                className="btn btn-danger btn-sm"
                                onClick={() => handleConfirmRejectProposal(p.id)}
                              >
                                Confirm Rejection
                              </button>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => setRejectingProposalId(null)}
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          /* Normal Proposal Display */
                          <>
                            <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', padding: '10px 14px', borderRadius: 'var(--radius-sm)', marginBottom: '8px' }}>
                              <div style={{ fontSize: '0.78rem', color: '#64748b', marginBottom: '4px' }}>
                                Raw OCR Proposed Text:
                              </div>
                              <pre style={{ margin: 0, fontFamily: 'monospace', fontSize: '0.9rem', whiteSpace: 'pre-wrap', color: '#1e293b' }}>
                                {p.proposed_text}
                              </pre>
                            </div>

                            {p.corrected_text && (
                              <div style={{ background: '#f0f9ff', border: '1px solid #bae6fd', borderLeft: '3px solid #0284c7', padding: '8px 12px', borderRadius: '0 4px 4px 0', marginBottom: '8px' }}>
                                <div style={{ fontSize: '0.78rem', color: '#0369a1', fontWeight: 600 }}>
                                  Teacher-Corrected Authoritative Text:
                                </div>
                                <div style={{ fontFamily: 'monospace', fontSize: '0.9rem', marginTop: '2px', color: '#0f172a' }}>
                                  {p.corrected_text}
                                </div>
                              </div>
                            )}

                            {/* Status Advisory / Rejection / Unmatched explanation */}
                            {p.status === 'rejected' && (
                              <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderLeft: '3px solid #ef4444', padding: '8px 12px', borderRadius: '0 4px 4px 0', marginBottom: '8px', fontSize: '0.85rem', color: '#991b1b' }}>
                                <strong>Rejected by Instructor:</strong> {p.rejection_reason || 'Excluded from assessment'}
                              </div>
                            )}

                            {p.status === 'unmatched' && (
                              <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderLeft: '3px solid #94a3b8', padding: '8px 12px', borderRadius: '0 4px 4px 0', marginBottom: '8px', fontSize: '0.85rem', color: '#475569' }}>
                                <strong>Unmatched Proposal:</strong>{' '}
                                {p.rejection_reason === 'QUESTION_NUMBER_OUT_OF_BOUNDS'
                                  ? 'The detected question number is outside the bounds of this assessment. Reassign to an existing question using "Reassign Question" or reject if extraneous.'
                                  : p.rejection_reason === 'NO_QUESTION_NUMBER_DETECTED'
                                  ? 'No question number could be identified in this OCR segment. Reassign manually using "Reassign Question".'
                                  : p.rejection_reason?.startsWith('SUPERSEDED_')
                                  ? 'Superseded by another approved proposal for this question.'
                                  : p.rejection_reason?.startsWith('CONTENT_MISMATCH_SUSPECTED')
                                  ? 'Subject / domain mismatch detected between student answer and this assessment.'
                                  : p.rejection_reason || 'Unmatched segment requiring manual question assignment.'}
                              </div>
                            )}

                            {p.status === 'needs_review' && p.rejection_reason && (
                              <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderLeft: '3px solid #f59e0b', padding: '8px 12px', borderRadius: '0 4px 4px 0', marginBottom: '8px', fontSize: '0.85rem', color: '#92400e' }}>
                                <strong>Teacher Review Advisory:</strong>{' '}
                                {p.rejection_reason === 'EXISTING_ANSWER_PRESENT'
                                  ? 'An answer is already recorded for this question. Approving will replace the existing submission response.'
                                  : p.rejection_reason === 'DUPLICATE_QUESTION_NUMBER'
                                  ? 'Multiple OCR segments matched this question number. Review and approve the correct student answer.'
                                  : p.rejection_reason === 'LOW_OCR_CONFIDENCE'
                                  ? 'Low character recognition confidence detected. Please verify before approving.'
                                  : p.rejection_reason?.startsWith('CONTENT_MISMATCH_SUSPECTED')
                                  ? '⚠️ Subject / domain mismatch: The student answer does not align with this question topic.'
                                  : p.rejection_reason}
                              </div>
                            )}

                            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '6px', flexWrap: 'wrap' }}>
                              <button
                                type="button"
                                className="btn btn-success btn-sm"
                                onClick={() => handleApproveProposal(p.id)}
                                disabled={p.status === 'approved' || p.status === 'rejected' || !p.question_id}
                                title={!p.question_id ? 'Unmatched proposal must be assigned to an assessment question before approval' : 'Approve proposal as authoritative answer'}
                              >
                                {p.status === 'approved' ? '✓ Approved' : 'Approve Match'}
                              </button>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => handleStartCorrectProposal(p)}
                              >
                                Correct OCR Text
                              </button>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => handleStartReassignProposal(p)}
                              >
                                Reassign Question
                              </button>
                              <button
                                type="button"
                                className="btn btn-danger btn-sm"
                                onClick={() => handleStartRejectProposal(p)}
                                disabled={p.status === 'rejected'}
                              >
                                {p.status === 'rejected' ? 'Rejected' : 'Reject'}
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
                </div>
              )}
            </div>
          )}

          {/* TAB 3: AI Diagnostic Analysis & Findings */}
          {activeTab === 'analysis' && (() => {
            let runsToDisplay = evaluationSummary?.runs || [];
            if (isAnswerSheetOnly && inferredItems.length > 0) {
              const activeQIds = new Set(inferredItems.map((i) => i.question_id).filter(Boolean));
              runsToDisplay = runsToDisplay.filter((r) => activeQIds.has(r.question_id));
            }
            const seenQ = new Set<number>();
            const dedupedRuns: typeof runsToDisplay = [];
            for (const run of runsToDisplay) {
              if (!seenQ.has(run.question_id)) {
                seenQ.add(run.question_id);
                dedupedRuns.push(run);
              }
            }
            const totalAccepted = dedupedRuns.reduce(
              (acc, r) => acc + (r.findings?.filter((f) => f.review_status === 'accepted')?.length || 0),
              0
            );

            return (
              <div className="tab-content analysis-tab-content">
                {emailStatusMsg && (
                  <div className="alert alert-success" style={{ marginBottom: '14px' }}>
                    ✓ {emailStatusMsg}
                  </div>
                )}

                <ResultsSpreadsheetTable
                  evaluationSummary={evaluationSummary}
                  inferredItems={inferredItems}
                />

                <div className="meta-bar">
                  <div className="meta-item">
                    <span className="meta-label">AI Engine:</span>
                    <code>{providerStatus?.evaluator_provider || evaluationSummary?.runs?.[0]?.evaluator_name || 'vllm'}</code>
                  </div>
                  {providerStatus?.evaluator_real && (
                    <div className="meta-item">
                      <span className="meta-label">Model:</span>
                      <span>{providerStatus.vllm_model || 'default-model'}</span>
                    </div>
                  )}
                  <div className="meta-item">
                    <span className="meta-label">Status:</span>
                    {aiHealth.status === 'online' || providerStatus?.vllm_reachable ? (
                      <span className="badge badge-success">● AI Online</span>
                    ) : (
                      <span className="badge" style={{ background: '#fef2f2', color: '#991b1b', border: '1px solid #fecaca' }}>● AI Offline</span>
                    )}
                  </div>
                  <div className="meta-item">
                    <span className="meta-label">Total Evaluation Runs:</span>
                    <span>{dedupedRuns.length}</span>
                  </div>
                  <div className="meta-item">
                    <span className="meta-label">Accepted Findings:</span>
                    <span className="badge badge-success">{totalAccepted}</span>
                  </div>
                </div>

                {(aiHealth.status === 'offline' || (providerStatus?.evaluator_real && !providerStatus?.vllm_reachable)) && (
                  <div className="alert alert-warning" style={{ margin: '16px 0', border: '1px solid #fcd34d', background: '#fffbeb', borderRadius: '8px', padding: '14px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, marginBottom: '6px', color: '#92400e' }}>
                      <span>ℹ️</span>
                      <span>AI is currently offline. Showing cached or mock evaluation.</span>
                    </div>
                    <div style={{ fontSize: '0.88rem', lineHeight: 1.5, color: '#78350f', marginBottom: '8px' }}>
                      Inksight is configured to evaluate using Groq / vLLM (model: <code>{aiHealth.model || providerStatus?.vllm_model || 'llama-3.3-70b-versatile'}</code>), but the endpoint is currently offline or unreachable. Evaluation automatically falls back to deterministic mock evaluation without crashing or blocking your session.
                    </div>
                    {aiHealth.error && (
                      <div style={{ fontSize: '0.82rem', background: '#fef3c7', padding: '8px 12px', borderRadius: '4px', fontFamily: 'monospace', color: '#92400e' }}>
                        Endpoint Status: {aiHealth.error}
                      </div>
                    )}
                  </div>
                )}

                {dedupedRuns.length > 0 ? (
                  dedupedRuns.map((run, rIdx) => {
                    const targetQ = assessmentQuestions.find((q) => q.id === run.question_id);
                    const inferredItem = inferredItems.find((i) => i.question_id === run.question_id);
                    const promptText = targetQ?.prompt || inferredItem?.inferred_question;
                    const marksVal = targetQ?.marks ?? inferredItem?.max_marks ?? 5;
                    const rubricVal = targetQ?.expected_answer || inferredItem?.expected_answer || inferredItem?.rubric;

                    return (
                      <div key={run.id} className="evaluation-run-block">
                        <div className="run-header" style={{ borderBottom: '1px solid #f1f5f9', paddingBottom: '10px', marginBottom: '12px' }}>
                          <div>
                            <h3 className="run-title" style={{ fontSize: '1.05rem', fontWeight: 700, color: '#0f172a' }}>
                              Question {rIdx + 1}{inferredItem?.concept_name ? `: ${inferredItem.concept_name}` : ''}
                            </h3>
                            {promptText && (
                              <div style={{ fontSize: '0.86rem', color: 'var(--text-secondary)', marginTop: '4px', lineHeight: 1.4 }}>
                                <div><strong>Prompt:</strong> {promptText} ({marksVal} pts)</div>
                                {rubricVal && (
                                  <div style={{ marginTop: '2px' }}>
                                    <strong>Expected Solution / Rubric:</strong> <code>{rubricVal}</code>
                                  </div>
                                )}
                              </div>
                            )}
                            {run.answer_text_snapshot && (
                              <div className="answer-snapshot" style={{ marginTop: '6px' }}>
                                <strong>Evaluated Student Answer (Authoritative):</strong> &ldquo;{run.answer_text_snapshot}&rdquo;
                              </div>
                            )}
                            {run.status === 'failed' && (
                              <div className="alert alert-danger" style={{ margin: '8px 0 0 0', fontSize: '0.82rem' }}>
                                <strong>Evaluation Failed:</strong> {run.error_message || 'Underlying evaluator error.'}
                              </div>
                            )}
                          </div>
                        </div>

                        <div className="findings-list">
                          {run.findings && run.findings.length > 0 ? (
                            run.findings.map((finding: EvaluationFinding) => {
                              const relatedProposal = proposals.find(
                                (p) => p.question_id === run.question_id
                              );
                              const ocrConf = relatedProposal?.confidence ?? result?.extraction?.confidence ?? null;

                              return (
                                <EvaluationFindingCard
                                  key={finding.id}
                                  finding={finding}
                                  ocrConfidence={ocrConf}
                                  isReviewing={reviewingFindingId === finding.id}
                                  isGenerating={generatingRemediationFor === finding.id}
                                  notesValue={findingReviewNotes[finding.id]}
                                  onNotesChange={(val) =>
                                    setFindingReviewNotes({
                                      ...findingReviewNotes,
                                      [finding.id]: val,
                                    })
                                  }
                                  onReview={(fId, action, notes, ack) =>
                                    handleReviewFinding(fId, action, notes, ack)
                                  }
                                  onGenerateRemediation={handleGenerateRemediation}
                                />
                              );
                            })
                          ) : (
                            <div className="empty-inline-state">
                              No conceptual misconceptions detected for this answer.
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="empty-inline-state">
                    No evaluation runs recorded yet. Ensure answer sheet proposals have been reviewed and approved.
                  </div>
                )}
              </div>
            );
          })()}

          {/* TAB 4: Targeted Remediation Items & Approval */}
          {activeTab === 'remediations' && (
            <div className="tab-content remediations-tab-content">
              <div className="meta-bar">
                <div className="meta-item">
                  <span className="meta-label">Generated Items:</span>
                  <span>{remediationItems.length}</span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Approved for Students:</span>
                  <span className="badge badge-success">
                    {remediationItems.filter((i) => i.review_status === 'approved' || i.review_status === 'edited').length}
                  </span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Pending Approval:</span>
                  <span className="badge badge-warning">
                    {remediationItems.filter((i) => i.review_status === 'pending_review').length}
                  </span>
                </div>
              </div>

              <div className="alert alert-info" style={{ fontSize: '0.85rem', marginBottom: '16px' }}>
                <strong>Instructor Quality Gate:</strong> Only practice items approved or edited by an instructor are delivered to students.
                Teacher answer keys and pedagogical rationales shown below are strictly hidden in student-facing views.
              </div>

              {loadingRemediations ? (
                <div className="loading-container">
                  <span className="spinner" />
                  <p>Loading targeted practice items...</p>
                </div>
              ) : remediationItems.length === 0 ? (
                <div className="empty-inline-state" style={{ padding: '36px 20px' }}>
                  <p style={{ fontWeight: 600, fontSize: '1rem', color: 'var(--text-primary)', marginBottom: '8px' }}>
                    No Remediation Practice Items Generated Yet
                  </p>
                  <p style={{ color: 'var(--text-secondary)', maxWidth: '520px', margin: '0 auto 16px auto', fontSize: '0.88rem' }}>
                    Go to the <strong>&ldquo;Diagnostic Findings &amp; Review&rdquo;</strong> tab, accept a diagnosed misconception finding, and click <strong>&ldquo;Generate Remediation Items&rdquo;</strong>.
                  </p>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={() => setActiveTab('analysis')}
                  >
                    View Diagnostic Findings
                  </button>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {remediationItems.map((item) => {
                    const isEditing = editingRemediationId === item.id;
                    const isReviewing = reviewingRemediationId === item.id;

                    const statusClass =
                      item.review_status === 'approved'
                        ? 'badge-success'
                        : item.review_status === 'edited'
                        ? 'badge-info'
                        : item.review_status === 'rejected'
                        ? 'badge-danger'
                        : 'badge-warning';

                    return (
                      <div
                        key={item.id}
                        className="finding-card"
                        style={{
                          background: 'var(--bg-secondary)',
                          border: `1px solid ${item.review_status === 'approved' || item.review_status === 'edited' ? 'rgba(16, 185, 129, 0.4)' : 'var(--border-color)'}`,
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', flexWrap: 'wrap', gap: '8px' }}>
                          <div>
                            <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
                              Item #{item.id}: {item.target_concept || 'Targeted Practice'}
                            </span>
                            <span style={{ marginLeft: '12px', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                              Type: <strong>{item.question_type}</strong> | Difficulty: <strong>{item.difficulty || 'medium'}</strong>
                            </span>
                          </div>
                          <span className={`badge ${statusClass}`}>
                            {item.review_status.replace('_', ' ').toUpperCase()}
                          </span>
                        </div>

                        {/* Inline Item Editor */}
                        {isEditing ? (
                          <div style={{ background: 'var(--bg-primary)', padding: '16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--primary)' }}>
                            <div className="form-group" style={{ marginBottom: '10px' }}>
                              <label className="form-label" style={{ fontSize: '0.82rem' }}>Student Practice Question Prompt</label>
                              <textarea
                                className="form-textarea"
                                rows={3}
                                value={editRemedPrompt}
                                onChange={(e) => setEditRemedPrompt(e.target.value)}
                                placeholder="Refine the student question prompt..."
                              />
                            </div>

                            <div className="form-group" style={{ marginBottom: '10px' }}>
                              <label className="form-label" style={{ fontSize: '0.82rem' }}>Teacher-Only Expected Answer Key</label>
                              <input
                                type="text"
                                className="form-input"
                                value={editRemedKey}
                                onChange={(e) => setEditRemedKey(e.target.value)}
                                placeholder="Expected correct response..."
                              />
                            </div>

                            <div className="form-group" style={{ marginBottom: '12px' }}>
                              <label className="form-label" style={{ fontSize: '0.82rem' }}>Pedagogical Rationale / Review Notes</label>
                              <textarea
                                className="form-textarea"
                                rows={2}
                                value={editRemedNotes}
                                onChange={(e) => setEditRemedNotes(e.target.value)}
                                placeholder="Rationale for pedagogical guidance..."
                              />
                            </div>

                            <div style={{ display: 'flex', gap: '8px' }}>
                              <button
                                type="button"
                                className="btn btn-success btn-sm"
                                onClick={() => handleSaveEditRemediation(item.id)}
                              >
                                Save Edits &amp; Approve for Delivery
                              </button>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => setEditingRemediationId(null)}
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          /* Normal Practice Item Display */
                          <>
                            {/* Student-facing prompt */}
                            <div style={{ marginBottom: '10px', fontSize: '0.95rem', color: '#0f172a', lineHeight: 1.5 }}>
                              <strong>Student Prompt:</strong> {item.edited_question_text || item.question_text || item.prompt}
                            </div>

                            {item.options && (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '12px', paddingLeft: '12px' }}>
                                {item.options.map((opt, oIdx) => (
                                  <div key={oIdx} style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                                    • {opt}
                                  </div>
                                ))}
                              </div>
                            )}

                            {/* Teacher-Only Verification Box */}
                            <div
                              style={{
                                background: '#f0f9ff',
                                border: '1px solid #bae6fd',
                                padding: '12px 14px',
                                borderRadius: 'var(--radius-sm)',
                                marginBottom: '12px',
                                fontSize: '0.86rem',
                              }}
                            >
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                                <span style={{ fontWeight: 600, color: '#0284c7', fontSize: '0.78rem' }}>
                                  🔒 Instructor Verification (Protected from Students)
                                </span>
                              </div>
                              <div>
                                <strong style={{ color: 'var(--success)' }}>Expected Answer Key:</strong>{' '}
                                <code>{item.edited_answer_key || item.teacher_answer_key || item.expected_answer || 'N/A'}</code>
                              </div>
                              <div style={{ marginTop: '4px', color: 'var(--text-secondary)' }}>
                                <strong>Pedagogical Rationale:</strong> {item.review_notes || item.teacher_rationale || item.explanation || 'Targeted concept reinforcement.'}
                              </div>
                              {item.uncertainty_note && (
                                <div style={{ marginTop: '4px', color: 'var(--warning)', fontSize: '0.8rem' }}>
                                  <strong>Generation Note:</strong> {item.uncertainty_note}
                                </div>
                              )}
                            </div>

                            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                              <button
                                type="button"
                                className="btn btn-success btn-sm"
                                onClick={() => handleReviewRemediationItem(item.id, 'approve')}
                                disabled={isReviewing || item.review_status === 'approved'}
                              >
                                {item.review_status === 'approved' ? '✓ Approved for Students' : 'Approve for Delivery'}
                              </button>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => handleStartEditRemediation(item)}
                              >
                                Edit &amp; Approve
                              </button>
                              <button
                                type="button"
                                className="btn btn-danger btn-sm"
                                onClick={() => handleReviewRemediationItem(item.id, 'reject')}
                                disabled={isReviewing || item.review_status === 'rejected'}
                              >
                                {item.review_status === 'rejected' ? 'Rejected' : 'Reject'}
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* TAB 5: Intervention Outcomes & Learning Loop */}
          {activeTab === 'outcomes' && (
            <div className="tab-content" style={{ marginTop: '16px' }}>
              <InterventionOutcomesView
                initialSubmissionId={result.upload?.submission_id}
              />
            </div>
          )}
        </div>
      ) : (
        /* Empty State */
        !isProcessing && (
          <div className="card empty-dashboard-card">
            <div className="empty-icon">📊</div>
            <h3>No Document Scanned Yet</h3>
            <p>
              Upload a scanned answer sheet PDF or image above and click <strong>&ldquo;Analyze Answer Sheet with AI&rdquo;</strong> to view real OCR extraction, teacher answer verification, and AI diagnostic findings.
            </p>
          </div>
        )
      )}

      <LiveCameraScanner
        isOpen={isCameraOpen}
        onClose={() => setIsCameraOpen(false)}
        onComplete={handleCameraScanComplete}
      />
    </div>
  );
};
