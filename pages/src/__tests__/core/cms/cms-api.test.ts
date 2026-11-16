import {describe, expect, it, vi} from 'vitest';

const {getMock} = vi.hoisted(() => ({
  getMock: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  api: {get: getMock},
  default: {get: getMock},
}));
// fetchCMSEmbedHosts lives in lib/api/embedHosts.ts, which uses the client module directly.
vi.mock('@/lib/api/api-client', () => ({
  api: {get: getMock},
}));

import {
  isCMSPageRedirectResponse,
  normalizeCMSRoute,
} from '@/features/cms/api';

describe('normalizeCMSRoute', () => {
  it('normalizes local CMS route segments', () => {
    expect(normalizeCMSRoute(' about//team-leads/ ')).toBe('/about/team-leads');
    expect(normalizeCMSRoute('/')).toBe('/');
  });

  it('normalizes empty and whitespace-only input to the root path', () => {
    expect(normalizeCMSRoute('')).toBe('/');
    expect(normalizeCMSRoute('   ')).toBe('/');
  });

  it('preserves case and safe punctuation used by legacy paths', () => {
    expect(normalizeCMSRoute('/FAQs')).toBe('/FAQs');
    expect(normalizeCMSRoute('/Archive.v1/~old+page')).toBe('/Archive.v1/~old+page');
    expect(normalizeCMSRoute('/Archive%2Ev1')).toBe('/Archive.v1');
  });

  it('rejects unsafe input instead of silently requesting the root page', () => {
    expect(() => normalizeCMSRoute('https://example.com/about')).toThrow();
    expect(() => normalizeCMSRoute('//example.com/about')).toThrow();
    expect(() => normalizeCMSRoute('/about\\team')).toThrow();
    expect(() => normalizeCMSRoute('/about?preview=true')).toThrow();
    expect(() => normalizeCMSRoute('/about/%2e%2e/admin')).toThrow();
  });

  it('rejects routes containing C0 or DEL control characters', () => {
    expect(() => normalizeCMSRoute('/about\u001fteams')).toThrow();
    expect(() => normalizeCMSRoute('/about\u007f')).toThrow();
  });

  it('rejects invalid percent encoding in a path segment', () => {
    expect(() => normalizeCMSRoute('/about/%zz')).toThrow(
      'CMS route contains invalid percent encoding.',
    );
  });

  it('rejects unsafe decoded path segments', () => {
    expect(() => normalizeCMSRoute('/about/.')).toThrow();
    expect(() => normalizeCMSRoute('/about/%2F')).toThrow();
    expect(() => normalizeCMSRoute('/about/%5C')).toThrow();
    expect(() => normalizeCMSRoute('/about/%00')).toThrow();
  });
});

describe('isCMSPageRedirectResponse', () => {
  it('only accepts permanent redirect payloads', () => {
    expect(isCMSPageRedirectResponse({redirect_to: '/faqs', permanent: true})).toBe(true);
    expect(isCMSPageRedirectResponse({
      slug: 'faqs',
      route: '/faqs',
      title: 'FAQs',
      page_css_class: '',
      meta_description: '',
      blocks: [],
    })).toBe(false);
  });
});
