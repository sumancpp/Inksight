import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { jsPDF } from 'jspdf';

export interface LiveCameraScannerProps {
  isOpen: boolean;
  onClose: () => void;
  onComplete: (file: File) => void;
}

export const compileImagesToPdf = async (dataUrls: string[]): Promise<File> => {
  const pdf = new jsPDF({
    orientation: 'portrait',
    unit: 'mm',
    format: 'a4',
  });

  for (let i = 0; i < dataUrls.length; i++) {
    if (i > 0) {
      pdf.addPage('a4', 'portrait');
    }
    // A4 width: 210mm, height: 297mm
    pdf.addImage(dataUrls[i], 'JPEG', 0, 0, 210, 297, undefined, 'FAST');
  }

  const blob = pdf.output('blob');
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const filename = `exam_camera_scan_${timestamp}.pdf`;
  if (typeof File !== 'undefined') {
    return new File([blob], filename, { type: 'application/pdf' });
  }
  const polyfillFile = blob as any;
  polyfillFile.name = filename;
  polyfillFile.lastModified = Date.now();
  return polyfillFile as File;
};

export const LiveCameraScanner: React.FC<LiveCameraScannerProps> = ({
  isOpen,
  onClose,
  onComplete,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const [stream, setStream] = useState<MediaStream | null>(null);
  const [capturedPages, setCapturedPages] = useState<string[]>([]);
  const [activePreviewIndex, setActivePreviewIndex] = useState<number | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [isCompiling, setIsCompiling] = useState<boolean>(false);
  const [facingMode, setFacingMode] = useState<'environment' | 'user'>('environment');

  // Start / stop camera stream based on modal open state
  useEffect(() => {
    if (!isOpen) {
      stopCamera();
      setCapturedPages([]);
      setActivePreviewIndex(null);
      setCameraError(null);
      return;
    }

    startCamera();

    return () => {
      stopCamera();
    };
  }, [isOpen, facingMode]);

  const startCamera = async () => {
    setCameraError(null);
    try {
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }

      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Camera access is not supported by your browser.');
      }

      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: facingMode },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
        audio: false,
      });

      setStream(mediaStream);
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
        videoRef.current.play().catch((err) => {
          console.warn('Video auto-play interrupted:', err);
        });
      }
    } catch (err: any) {
      console.error('Camera initialization error:', err);
      setCameraError(
        err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError'
          ? 'Camera permission was denied. Please allow camera access in your browser settings to scan documents.'
          : err.message || 'Unable to access device camera.'
      );
    }
  };

  const stopCamera = () => {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      setStream(null);
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  };

  // Flip between front and back camera
  const handleFlipCamera = () => {
    setFacingMode((prev) => (prev === 'environment' ? 'user' : 'environment'));
  };

  // Capture current video frame
  const handleCapturePage = () => {
    if (!videoRef.current || !canvasRef.current) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;

    const width = video.videoWidth || 1280;
    const height = video.videoHeight || 720;

    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.drawImage(video, 0, 0, width, height);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.92);

    const updated = [...capturedPages, dataUrl];
    setCapturedPages(updated);
    setActivePreviewIndex(updated.length - 1); // Freeze & preview newly captured page
  };

  // Add Another Page: clear active preview, resume live camera
  const handleAddAnotherPage = () => {
    setActivePreviewIndex(null);
    if (!stream) {
      startCamera();
    }
  };

  // Retake current preview page
  const handleRetakeCurrentPage = () => {
    if (activePreviewIndex !== null) {
      const updated = capturedPages.filter((_, idx) => idx !== activePreviewIndex);
      setCapturedPages(updated);
      setActivePreviewIndex(null);
    }
  };

  // Finish & Analyze: Compile pages to PDF and pass to onComplete
  const handleFinishAndAnalyze = async () => {
    if (capturedPages.length === 0) return;

    setIsCompiling(true);
    try {
      const pdfFile = await compileImagesToPdf(capturedPages);
      stopCamera();
      onComplete(pdfFile);
      onClose();
    } catch (err) {
      console.error('Failed to compile camera scan to PDF:', err);
      setCameraError('Failed to compile pages into PDF. Please try again.');
    } finally {
      setIsCompiling(false);
    }
  };

  if (!isOpen) return null;

  const isPreviewing = activePreviewIndex !== null && capturedPages[activePreviewIndex];

  const modalContent = (
    <div
      data-testid="camera-scanner-modal"
      className="camera-scanner-overlay"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        zIndex: 9999,
        backgroundColor: '#000000',
        display: 'flex',
        flexDirection: 'column',
        color: '#ffffff',
      }}
    >
      {/* Hidden processing canvas */}
      <canvas ref={canvasRef} style={{ display: 'none' }} />

      {/* Top Header Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '16px 24px',
          background: 'rgba(15, 23, 42, 0.8)',
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '10px',
              background: 'linear-gradient(135deg, #0284c7, #0d9488)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
              <circle cx="12" cy="13" r="4" />
            </svg>
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: '#f8fafc' }}>
              Live Exam Page Scanner
            </h3>
            <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
              {capturedPages.length === 0
                ? 'Align page within the frame and capture'
                : `${capturedPages.length} ${capturedPages.length === 1 ? 'Page' : 'Pages'} Captured`}
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {!isPreviewing && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleFlipCamera}
              title="Flip between front and rear camera"
              style={{
                background: 'rgba(255, 255, 255, 0.1)',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                color: '#fff',
                fontSize: '0.82rem',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
              </svg>
              <span>Flip Camera</span>
            </button>
          )}

          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={onClose}
            style={{
              color: '#94a3b8',
              fontSize: '1.4rem',
              lineHeight: 1,
              padding: '4px 10px',
            }}
            title="Cancel & Close Scanner"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Main Viewport: Live Stream or Frozen Page Preview */}
      <div
        style={{
          flex: 1,
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          background: '#090d16',
        }}
      >
        {cameraError ? (
          <div
            style={{
              maxWidth: '460px',
              padding: '24px',
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid #ef4444',
              borderRadius: '12px',
              textAlign: 'center',
              color: '#fca5a5',
            }}
          >
            <div style={{ fontSize: '2rem', marginBottom: '8px' }}>⚠️</div>
            <h4 style={{ margin: '0 0 8px 0', color: '#ef4444' }}>Camera Unavailable</h4>
            <p style={{ fontSize: '0.9rem', lineHeight: 1.5, margin: '0 0 16px 0' }}>{cameraError}</p>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={startCamera}
              style={{ background: '#fff', color: '#0f172a' }}
            >
              Retry Camera Access
            </button>
          </div>
        ) : isPreviewing ? (
          /* Frozen Captured Page Preview */
          <div
            style={{
              position: 'relative',
              width: '100%',
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '20px',
            }}
          >
            <img
              src={capturedPages[activePreviewIndex]}
              alt={`Captured Page ${activePreviewIndex + 1}`}
              style={{
                maxWidth: '90%',
                maxHeight: '90%',
                objectFit: 'contain',
                borderRadius: '8px',
                boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
                border: '2px solid rgba(255, 255, 255, 0.2)',
              }}
            />
            <div
              style={{
                position: 'absolute',
                top: '28px',
                background: 'rgba(15, 23, 42, 0.75)',
                padding: '6px 14px',
                borderRadius: '20px',
                fontSize: '0.85rem',
                fontWeight: 600,
                color: '#38bdf8',
                border: '1px solid rgba(56, 189, 248, 0.3)',
              }}
            >
              Previewing Page {activePreviewIndex + 1} of {capturedPages.length}
            </div>
          </div>
        ) : (
          /* Live Camera Feed with Document Alignment Guide */
          <div
            style={{
              position: 'relative',
              width: '100%',
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
              }}
            />

            {/* Document Target Alignment Guide Overlay */}
            <div
              className="scanner-alignment-guide"
              style={{
                position: 'absolute',
                width: 'min(88%, 560px)',
                height: 'min(80%, 760px)',
                border: '2px dashed rgba(56, 189, 248, 0.65)',
                borderRadius: '16px',
                pointerEvents: 'none',
                boxShadow: '0 0 0 9999px rgba(0, 0, 0, 0.35)',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                padding: '16px',
              }}
            >
              <div
                style={{
                  alignSelf: 'center',
                  background: 'rgba(15, 23, 42, 0.8)',
                  padding: '4px 12px',
                  borderRadius: '12px',
                  fontSize: '0.78rem',
                  color: '#bae6fd',
                  fontWeight: 600,
                }}
              >
                📄 Align exam page within frame
              </div>
              <div
                style={{
                  alignSelf: 'center',
                  background: 'rgba(15, 23, 42, 0.8)',
                  padding: '4px 12px',
                  borderRadius: '12px',
                  fontSize: '0.78rem',
                  color: '#94a3b8',
                }}
              >
                Page {capturedPages.length + 1}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Captured Pages Thumbnail Strip */}
      {capturedPages.length > 0 && (
        <div
          style={{
            background: 'rgba(15, 23, 42, 0.9)',
            borderTop: '1px solid rgba(255, 255, 255, 0.1)',
            padding: '10px 20px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            overflowX: 'auto',
          }}
        >
          <span style={{ fontSize: '0.8rem', color: '#94a3b8', whiteSpace: 'nowrap' }}>
            Captured Pages:
          </span>
          {capturedPages.map((page, idx) => (
            <div
              key={idx}
              onClick={() => setActivePreviewIndex(idx)}
              style={{
                position: 'relative',
                cursor: 'pointer',
                border: activePreviewIndex === idx ? '2px solid #0284c7' : '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: '6px',
                overflow: 'hidden',
                flexShrink: 0,
                width: '44px',
                height: '60px',
              }}
              title={`View Page ${idx + 1}`}
            >
              <img src={page} alt={`Page ${idx + 1}`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              <span
                style={{
                  position: 'absolute',
                  bottom: 0,
                  right: 0,
                  left: 0,
                  background: 'rgba(0, 0, 0, 0.7)',
                  color: '#fff',
                  fontSize: '0.65rem',
                  textAlign: 'center',
                  fontWeight: 700,
                }}
              >
                p.{idx + 1}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Bottom Action Control Bar */}
      <div
        className="scanner-bottom-bar"
        style={{
          padding: '16px 20px',
          paddingBottom: 'max(16px, env(safe-area-inset-bottom))',
          background: 'rgba(15, 23, 42, 0.95)',
          borderTop: '1px solid rgba(255, 255, 255, 0.1)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div>
          {isPreviewing ? (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleRetakeCurrentPage}
              style={{
                background: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid rgba(239, 68, 68, 0.4)',
                color: '#f87171',
                fontSize: '0.86rem',
              }}
            >
              🗑️ Retake Page
            </button>
          ) : (
            <span style={{ fontSize: '0.85rem', color: '#94a3b8' }}>
              Hold steady for sharp OCR clarity
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
          {isPreviewing ? (
            <>
              {/* Add Another Page Button */}
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleAddAnotherPage}
                style={{
                  background: 'rgba(255, 255, 255, 0.12)',
                  border: '1px solid rgba(255, 255, 255, 0.25)',
                  color: '#ffffff',
                  fontWeight: 600,
                  padding: '10px 20px',
                  fontSize: '0.92rem',
                }}
              >
                + Add Another Page
              </button>

              {/* Finish & Analyze Button */}
              <button
                type="button"
                className="btn btn-primary btn-cta-gradient"
                onClick={handleFinishAndAnalyze}
                disabled={isCompiling}
                style={{
                  padding: '10px 24px',
                  fontSize: '0.95rem',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                {isCompiling ? (
                  <>
                    <span className="spinner" />
                    <span>Compiling Multi-Page PDF...</span>
                  </>
                ) : (
                  <>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                    </svg>
                    <span>Finish &amp; Analyze ({capturedPages.length} {capturedPages.length === 1 ? 'Page' : 'Pages'})</span>
                  </>
                )}
              </button>
            </>
          ) : (
            /* Live Camera Shutter Capture Button */
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleCapturePage}
              disabled={Boolean(cameraError)}
              style={{
                width: '64px',
                height: '64px',
                borderRadius: '50%',
                background: 'linear-gradient(135deg, #0284c7, #0d9488)',
                border: '4px solid rgba(255, 255, 255, 0.8)',
                boxShadow: '0 0 20px rgba(2, 132, 199, 0.5)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                transition: 'transform 0.15s ease',
              }}
              title="Capture Page"
            >
              <div
                style={{
                  width: '24px',
                  height: '24px',
                  borderRadius: '50%',
                  background: '#ffffff',
                }}
              />
            </button>
          )}
        </div>
      </div>
    </div>
  );

  if (isMounted && typeof document !== 'undefined' && document.body) {
    return createPortal(modalContent, document.body);
  }

  return modalContent;
};
