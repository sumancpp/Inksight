import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { AnswerSheetUpload, Assessment, OCRExtraction, Submission } from '../../types';
import { validateUploadFile } from '../../utils/fileValidation';

export const SubmissionsOCRView: React.FC = () => {
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<number | ''>('');
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [selectedSubmission, setSelectedSubmission] = useState<Submission | null>(null);

  const [uploads, setUploads] = useState<AnswerSheetUpload[]>([]);
  const [selectedUpload, setSelectedUpload] = useState<AnswerSheetUpload | null>(null);
  const [extraction, setExtraction] = useState<OCRExtraction | null>(null);

  const [fileToUpload, setFileToUpload] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    const loadAssessments = async () => {
      try {
        const res = await api.getAssessments();
        setAssessments(res.items);
        if (res.items.length > 0) {
          setSelectedAssessmentId(res.items[0].id);
        }
      } catch (err: any) {
        setError(err.message || 'Failed to load assessments.');
      }
    };
    loadAssessments();
  }, []);

  useEffect(() => {
    if (selectedAssessmentId) {
      loadSubmissions(Number(selectedAssessmentId));
    }
  }, [selectedAssessmentId]);

  const loadSubmissions = async (assessmentId: number) => {
    try {
      const res = await api.getSubmissions(assessmentId);
      setSubmissions(res.items);
      if (res.items.length > 0) {
        handleSelectSubmission(res.items[0]);
      } else {
        setSelectedSubmission(null);
        setUploads([]);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch submissions.');
    }
  };

  const handleSelectSubmission = async (sub: Submission) => {
    setSelectedSubmission(sub);
    setExtraction(null);
    setSelectedUpload(null);
    try {
      const uploadsRes = await api.getAnswerSheets(sub.id);
      setUploads(uploadsRes.items);
      if (uploadsRes.items.length > 0) {
        handleSelectUpload(uploadsRes.items[0]);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load uploads for submission.');
    }
  };

  const handleSelectUpload = async (upload: AnswerSheetUpload) => {
    setSelectedUpload(upload);
    try {
      const extractionRes = await api.getOCRExtraction(upload.id);
      setExtraction(extractionRes);
    } catch {
      // If not yet extracted, extraction may be 404
      setExtraction(null);
    }
  };

  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSubmission || !fileToUpload) return;

    const validation = validateUploadFile(fileToUpload);
    if (!validation.valid) {
      setError(validation.error || 'Invalid file.');
      return;
    }

    setUploading(true);
    setError(null);
    setSuccess(null);

    try {
      const uploaded = await api.uploadAnswerSheet(selectedSubmission.id, fileToUpload);
      setSuccess(`Answer sheet "${uploaded.original_filename}" uploaded successfully.`);
      setFileToUpload(null);
      // Reload uploads
      const uploadsRes = await api.getAnswerSheets(selectedSubmission.id);
      setUploads(uploadsRes.items);
      handleSelectUpload(uploaded);
    } catch (err: any) {
      setError(err.message || 'Failed to upload answer sheet file.');
    } finally {
      setUploading(false);
    }
  };

  const handleTriggerOCR = async () => {
    if (!selectedUpload) return;
    setProcessing(true);
    setError(null);
    setSuccess(null);

    try {
      await api.triggerOCRProcess(selectedUpload.id);
      setSuccess('OCR extraction triggered (running in background).');
      // Wait a moment then refresh
      setTimeout(async () => {
        if (selectedSubmission) {
          const uploadsRes = await api.getAnswerSheets(selectedSubmission.id);
          setUploads(uploadsRes.items);
          const current = uploadsRes.items.find((u) => u.id === selectedUpload.id);
          if (current) handleSelectUpload(current);
        }
        setProcessing(false);
      }, 1500);
    } catch (err: any) {
      setError(err.message || 'Failed to trigger OCR processing.');
      setProcessing(false);
    }
  };

  return (
    <div>
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Submissions & Answer Sheet OCR</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          Inspect student submissions, upload scanned answer sheets, and trigger automated OCR extraction.
        </p>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      <div className="card" style={{ padding: '16px 20px', marginBottom: '20px' }}>
        <label className="form-label" style={{ marginBottom: '6px' }}>Select Assessment</label>
        <select
          className="form-select"
          style={{ maxWidth: '400px' }}
          value={selectedAssessmentId}
          onChange={(e) => setSelectedAssessmentId(Number(e.target.value))}
        >
          {assessments.map((a) => (
            <option key={a.id} value={a.id}>
              {a.title} (ID #{a.id})
            </option>
          ))}
        </select>
      </div>

      <div className="grid-2" style={{ alignItems: 'flex-start' }}>
        {/* Left: Submissions list */}
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Student Submissions ({submissions.length})</h3>
          </div>
          {submissions.length === 0 ? (
            <div className="empty-state">No submissions found for this assessment.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {submissions.map((s) => (
                <div
                  key={s.id}
                  onClick={() => handleSelectSubmission(s)}
                  style={{
                    padding: '12px 16px',
                    borderRadius: 'var(--radius-sm)',
                    background: selectedSubmission?.id === s.id ? 'var(--primary-light)' : 'var(--bg-primary)',
                    border: `1px solid ${selectedSubmission?.id === s.id ? 'var(--primary)' : 'var(--border-color)'}`,
                    cursor: 'pointer',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600 }}>Submission #{s.id}</div>
                    <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                      Student ID: {s.student_id} | Created: {new Date(s.created_at).toLocaleDateString()}
                    </div>
                  </div>
                  <span className={`badge badge-${s.status === 'reviewed' ? 'success' : s.status === 'submitted' ? 'info' : 'warning'}`}>
                    {s.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Answer Sheet Upload & OCR */}
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">
              {selectedSubmission ? `Answer Sheets (Sub #${selectedSubmission.id})` : 'Select a Submission'}
            </h3>
          </div>

          {selectedSubmission && (
            <>
              {/* Upload form */}
              <form onSubmit={handleFileUpload} style={{ marginBottom: '20px' }}>
                <div className="form-group">
                  <label className="form-label">Upload Answer Sheet (.pdf, .png, .jpg)</label>
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <input
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg"
                      className="form-input"
                      style={{ padding: '6px 10px' }}
                      onChange={(e) => setFileToUpload(e.target.files?.[0] || null)}
                      required
                    />
                    <button type="submit" className="btn btn-primary" disabled={uploading || !fileToUpload}>
                      {uploading ? <span className="spinner" /> : 'Upload'}
                    </button>
                  </div>
                </div>
              </form>

              {/* Uploads list */}
              {uploads.length === 0 ? (
                <div className="empty-state">No answer sheets uploaded yet.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {uploads.map((u) => (
                    <div
                      key={u.id}
                      onClick={() => handleSelectUpload(u)}
                      style={{
                        padding: '12px 14px',
                        background: selectedUpload?.id === u.id ? 'var(--bg-tertiary)' : 'var(--bg-primary)',
                        border: `1px solid ${selectedUpload?.id === u.id ? 'var(--primary)' : 'var(--border-color)'}`,
                        borderRadius: 'var(--radius-sm)',
                        cursor: 'pointer',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                        <span style={{ fontWeight: 600 }}>{u.original_filename}</span>
                        <span className="badge badge-info">{u.upload_status}</span>
                      </div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                        Size: {(u.file_size_bytes / 1024).toFixed(1)} KB | Uploaded: {new Date(u.uploaded_at).toLocaleTimeString()}
                      </div>
                    </div>
                  ))}

                  {/* OCR Actions & Extraction result */}
                  {selectedUpload && (
                    <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px solid var(--border-color)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                        <span style={{ fontWeight: 600 }}>OCR Status: <span className="badge badge-info">{selectedUpload.upload_status}</span></span>
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={handleTriggerOCR}
                          disabled={processing}
                        >
                          {processing ? <span className="spinner" /> : 'Run Mock OCR Extraction'}
                        </button>
                      </div>

                      <div className="alert alert-info" style={{ fontSize: '0.82rem', padding: '8px 12px' }}>
                        Note: OCR extraction currently uses deterministic local mock adapter for testing.
                      </div>

                      {extraction && (
                        <div style={{ background: 'var(--bg-primary)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
                          <div style={{ fontWeight: 600, fontSize: '0.88rem', marginBottom: '6px' }}>
                            Extracted Text:
                          </div>
                          <pre style={{ fontSize: '0.82rem', whiteSpace: 'pre-wrap', color: 'var(--text-primary)', fontFamily: 'monospace' }}>
                            {extraction.extracted_text || 'No text extracted.'}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
