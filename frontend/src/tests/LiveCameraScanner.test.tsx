import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { LiveCameraScanner, compileImagesToPdf } from '../components/camera/LiveCameraScanner';

describe('LiveCameraScanner Component & PDF Compiler', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('compileImagesToPdf compiles data URLs into a single multi-page PDF File', async () => {
    // 1x1 transparent JPEG base64
    const sampleImage =
      'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=';

    const file = await compileImagesToPdf([sampleImage, sampleImage]);

    expect(file).toBeDefined();
    expect(file.type).toBe('application/pdf');
    expect(file.name).toMatch(/^exam_camera_scan_.*\.pdf$/);
    expect(file.size).toBeGreaterThan(0);
  });

  it('does not render modal content when isOpen is false', () => {
    const html = renderToStaticMarkup(
      <LiveCameraScanner isOpen={false} onClose={() => {}} onComplete={() => {}} />
    );
    expect(html).toBe('');
  });

  it('renders camera viewport and alignment guide when isOpen is true', () => {
    const html = renderToStaticMarkup(
      <LiveCameraScanner isOpen={true} onClose={() => {}} onComplete={() => {}} />
    );
    expect(html).toContain('Live Exam Page Scanner');
    expect(html).toContain('Align exam page within frame');
    expect(html).toContain('Capture Page');
  });
});
