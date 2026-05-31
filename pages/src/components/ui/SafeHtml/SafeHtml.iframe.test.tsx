import {render} from '@testing-library/react';
import {describe, expect, it} from 'vitest';
import {SafeHtml} from './SafeHtml';

/**
 * Coverage for the DOMPurify `uponSanitizeElement` iframe allowlist hook
 * registered in SafeHtml.tsx. The existing tests assert script stripping;
 * these assert the iframe host allowlist / denylist.
 */

describe('SafeHtml iframe allowlist', () => {
  it('keeps iframes from allowed video hosts', () => {
    const html = `<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" allowfullscreen></iframe>`;
    const {container} = render(<SafeHtml html={html} />);
    const iframe = container.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute('src')).toContain('youtube.com/embed/');
  });

  it('keeps Vimeo iframes', () => {
    const html = `<iframe src="https://player.vimeo.com/video/1234"></iframe>`;
    const {container} = render(<SafeHtml html={html} />);
    expect(container.querySelector('iframe')).not.toBeNull();
  });

  it('removes iframes from untrusted hosts', () => {
    const html = `<iframe src="https://evil.example.com/frame"></iframe>`;
    const {container} = render(<SafeHtml html={html} />);
    expect(container.querySelector('iframe')).toBeNull();
  });

  it('removes iframes with unparseable src', () => {
    const html = `<iframe src="not-a-url"></iframe>`;
    const {container} = render(<SafeHtml html={html} />);
    expect(container.querySelector('iframe')).toBeNull();
  });
});
