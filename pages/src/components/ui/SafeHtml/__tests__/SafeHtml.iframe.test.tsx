import {render, waitFor} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';

const fetchCMSEmbedHosts = vi.hoisted(() => vi.fn());

vi.mock('@/features/cms/api', () => ({
  fetchCMSEmbedHosts,
}));

import {SafeHtml} from '../SafeHtml';

/**
 * The public allowlist is loaded once. Until that request resolves, SafeHtml
 * strips every iframe rather than briefly rendering an unverified host.
 */

describe('SafeHtml iframe allowlist', () => {
  it('strips iframes until the one-time public host request is ready', async () => {
    let resolveHosts!: (value: {
      hosts: string[];
      revision: string;
    }) => void;
    fetchCMSEmbedHosts.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveHosts = resolve;
      }),
    );
    const html = `<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" allowfullscreen></iframe>`;
    const {container} = render(<SafeHtml html={html} />);
    expect(container.querySelector('iframe')).toBeNull();

    resolveHosts({
      hosts: [
        'youtube.com',
        '*.youtube.com',
        'player.vimeo.com',
      ],
      revision: 'hosts-v1',
    });

    await waitFor(() =>
      expect(container.querySelector('iframe')).not.toBeNull(),
    );
    expect(container.querySelector('iframe')?.getAttribute('src')).toContain(
      'youtube.com/embed/',
    );
    expect(fetchCMSEmbedHosts).toHaveBeenCalledTimes(1);
  });

  it('matches exact and wildcard hosts with wildcard subdomains only', () => {
    const {container} = render(
      <SafeHtml
        html={[
          '<iframe src="https://player.vimeo.com/video/1234"></iframe>',
          '<iframe src="https://m.youtube.com/embed/abc"></iframe>',
          '<iframe src="https://youtube.com/embed/abc"></iframe>',
        ].join('')}
      />,
    );
    expect(container.querySelectorAll('iframe')).toHaveLength(3);

    const wildcardOnly = render(
      <SafeHtml html={'<iframe src="https://vimeo.com/video/1234"></iframe>'} />,
    );
    expect(wildcardOnly.container.querySelector('iframe')).toBeNull();
    expect(fetchCMSEmbedHosts).toHaveBeenCalledTimes(1);
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

  it('removes non-HTTPS iframes even when their host is allowed', () => {
    const html = `<iframe src="http://youtube.com/embed/abc"></iframe>`;
    const {container} = render(<SafeHtml html={html} />);
    expect(container.querySelector('iframe')).toBeNull();
  });
});
