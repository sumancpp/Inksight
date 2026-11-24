import { describe, it, expect } from 'vitest';
import { validateUploadFile } from '../utils/fileValidation';

describe('Frontend File Validation (validateUploadFile)', () => {
  it('accepts valid PDF within 15MB', () => {
    const file = { name: 'student_work.pdf', type: 'application/pdf', size: 5 * 1024 * 1024 } as File;
    const result = validateUploadFile(file);
    expect(result.valid).toBe(true);
    expect(result.error).toBeUndefined();
  });

  it('accepts valid PNG image', () => {
    const file = { name: 'scan_page.png', type: 'image/png', size: 2 * 1024 * 1024 } as File;
    const result = validateUploadFile(file);
    expect(result.valid).toBe(true);
  });

  it('accepts valid JPEG image', () => {
    const file = { name: 'scan_page.jpg', type: 'image/jpeg', size: 1024 } as File;
    const result = validateUploadFile(file);
    expect(result.valid).toBe(true);
  });

  it('rejects disallowed file extensions (e.g. .txt)', () => {
    const file = { name: 'answers.txt', type: 'text/plain', size: 1024 } as File;
    const result = validateUploadFile(file);
    expect(result.valid).toBe(false);
    expect(result.error).toContain('Invalid file extension');
  });

  it('rejects disallowed MIME type even with valid extension', () => {
    const file = { name: 'script.pdf', type: 'application/x-sh', size: 1024 } as File;
    const result = validateUploadFile(file);
    expect(result.valid).toBe(false);
    expect(result.error).toContain('Invalid file type');
  });

  it('rejects oversized files > 15MB', () => {
    const file = { name: 'huge_document.pdf', type: 'application/pdf', size: 20 * 1024 * 1024 } as File;
    const result = validateUploadFile(file);
    expect(result.valid).toBe(false);
    expect(result.error).toContain('exceeds maximum allowed limit of 15 MB');
  });

  it('rejects missing or empty file', () => {
    const result = validateUploadFile(null as any);
    expect(result.valid).toBe(false);
    expect(result.error).toBe('No file selected.');
  });
});
