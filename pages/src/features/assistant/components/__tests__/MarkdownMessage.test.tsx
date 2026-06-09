import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {MarkdownMessage} from '../MarkdownMessage';
import {isSafeHref} from '../markdownLinks';

// react-markdown loads through a lazy/Suspense boundary, so every assertion
// here must await the async render (findBy*), not the synchronous queries.

describe('MarkdownMessage', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders bold, italic, lists, and inline code', async () => {
    render(<MarkdownMessage content={'**bold** and *italic*\n\n- one\n- two\n\n`code`'} />);

    expect(await screen.findByText('bold')).toHaveProperty('tagName', 'STRONG');
    expect(screen.getByText('italic')).toHaveProperty('tagName', 'EM');
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByText('code')).toHaveProperty('tagName', 'CODE');
  });

  it('renders safe links with target=_blank and rel=noopener noreferrer', async () => {
    render(<MarkdownMessage content={'[example](https://example.com)'} />);

    const link = await screen.findByRole('link', {name: 'example'});
    expect(link).toHaveAttribute('href', 'https://example.com');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('renders tel: links as anchors (aligned with the site-wide safeHref allowlist)', async () => {
    render(<MarkdownMessage content={'[Call us](tel:+12095551234)'} />);

    const link = await screen.findByRole('link', {name: 'Call us'});
    expect(link).toHaveAttribute('href', 'tel:+12095551234');
  });

  it('neutralizes javascript: links to inert text (no anchor)', async () => {
    render(<MarkdownMessage content={'[click](javascript:alert(1))'} />);

    // The text still renders, but not as a link, and never with a javascript: href.
    expect(await screen.findByText('click')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(document.querySelector('a[href^="javascript:"]')).toBeNull();
  });

  it('escapes raw <script> HTML instead of executing it', async () => {
    render(<MarkdownMessage content={'before <script>alert(1)</script> after'} />);

    // The raw markup is shown as escaped text; no real <script> node exists.
    expect(await screen.findByText(/<script>alert\(1\)<\/script>/)).toBeInTheDocument();
    expect(document.querySelector('script')).toBeNull();
  });

  it('escapes raw <img onerror> HTML instead of rendering an element', async () => {
    render(<MarkdownMessage content={'<img src=x onerror=alert(1)>'} />);

    expect(await screen.findByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument();
    expect(document.querySelector('img')).toBeNull();
  });
});

describe('isSafeHref', () => {
  it('accepts whitelisted protocols', () => {
    expect(isSafeHref('https://example.com')).toBe(true);
    expect(isSafeHref('http://example.com')).toBe(true);
    expect(isSafeHref('mailto:hi@example.com')).toBe(true);
    expect(isSafeHref('tel:+12095551234')).toBe(true);
  });

  it('rejects disallowed protocols and empty input', () => {
    expect(isSafeHref('javascript:alert(1)')).toBe(false);
    expect(isSafeHref('data:text/html,x')).toBe(false);
    expect(isSafeHref(undefined)).toBe(false);
    expect(isSafeHref('')).toBe(false);
  });

  it('rejects unparseable URLs (URL constructor throws)', () => {
    // A bare scheme with no host is rejected by the URL parser even with a base.
    expect(isSafeHref('http://')).toBe(false);
  });
});
