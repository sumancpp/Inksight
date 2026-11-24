/**
 * File validation utilities for upload security and size limits.
 */

export const ALLOWED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg'];
export const ALLOWED_MIME_TYPES = [
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/pjpeg',
];
export const DEFAULT_MAX_UPLOAD_SIZE_MB = 15;

export interface ValidationResult {
  valid: boolean;
  error?: string;
}

/**
 * Validates a file before submitting it to the backend.
 * Checks extension, MIME type (if present), and maximum size.
 */
export function validateUploadFile(
  file: File,
  maxMb: number = DEFAULT_MAX_UPLOAD_SIZE_MB
): ValidationResult {
  if (!file) {
    return { valid: false, error: 'No file selected.' };
  }

  const filename = file.name || '';
  const lastDot = filename.lastIndexOf('.');
  const ext = lastDot !== -1 ? filename.slice(lastDot).toLowerCase() : '';

  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return {
      valid: false,
      error: `Invalid file extension "${ext || 'none'}". Allowed types: .pdf, .png, .jpg, .jpeg.`,
    };
  }

  if (file.type && !ALLOWED_MIME_TYPES.includes(file.type.toLowerCase())) {
    return {
      valid: false,
      error: `Invalid file type "${file.type}". Allowed types: PDF documents and PNG/JPEG images.`,
    };
  }

  const maxBytes = maxMb * 1024 * 1024;
  if (file.size > maxBytes) {
    const fileSizeMb = (file.size / (1024 * 1024)).toFixed(2);
    return {
      valid: false,
      error: `File size (${fileSizeMb} MB) exceeds maximum allowed limit of ${maxMb} MB.`,
    };
  }

  return { valid: true };
}
