import {cleanup, render} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it} from 'vitest';

import {usePageTitle, type PageMetaOptions} from '@/hooks/usePageTitle';

const SITE_DESCRIPTION = "Innovate to Grow is UC Merced School of Engineering's experiential learning program.";

function Page({title, ...options}: {title: string | null} & PageMetaOptions) {
  usePageTitle(title, options);
  return null;
}

const meta = (selector: string) => document.head.querySelector<HTMLMetaElement>(selector)?.content ?? null;

describe('usePageTitle', () => {
  beforeEach(() => {
    document.head.innerHTML = `<meta name="description" content="${SITE_DESCRIPTION}">`;
    document.title = 'Innovate to Grow | School of Engineering';
  });

  afterEach(cleanup);

  it('names the tab and og:title after the page', () => {
    render(<Page title="Current Projects" />);

    expect(document.title).toBe('Current Projects | Innovate to Grow');
    expect(meta('meta[property="og:title"]')).toBe('Current Projects');
  });

  it('keeps the current title for a blank one, and leaves the description and robots alone', () => {
    render(<Page title="  " />);

    expect(document.title).toBe('Innovate to Grow | School of Engineering');
    expect(meta('meta[name="description"]')).toBe(SITE_DESCRIPTION);
    expect(document.head.querySelector('meta[name="robots"]')).toBeNull();
  });

  it('marks a not-found page noindex, and drops the mark when the page goes', () => {
    const {unmount} = render(<Page title="Project not found" noindex />);

    expect(document.title).toBe('Project not found | Innovate to Grow');
    expect(meta('meta[name="robots"]')).toBe('noindex');

    unmount();
    expect(document.head.querySelector('meta[name="robots"]')).toBeNull();
  });

  it("describes the page, and restores the site's description when it goes", () => {
    const {unmount} = render(<Page title="A project" description="  A drone that plants trees.  " />);

    expect(meta('meta[name="description"]')).toBe('A drone that plants trees.');
    expect(meta('meta[property="og:description"]')).toBe('A drone that plants trees.');

    unmount();
    expect(meta('meta[name="description"]')).toBe(SITE_DESCRIPTION);
    expect(meta('meta[property="og:description"]')).toBe(SITE_DESCRIPTION);
  });

  it('keeps noindex while any page still asks for it', () => {
    const first = render(<Page title="Shared list" noindex />);
    const second = render(<Page title="Shared list unavailable" noindex />);

    second.unmount();
    expect(meta('meta[name="robots"]')).toBe('noindex');

    first.unmount();
    expect(document.head.querySelector('meta[name="robots"]')).toBeNull();
  });
});
