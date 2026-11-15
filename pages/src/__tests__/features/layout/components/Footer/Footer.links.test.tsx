import {cleanup, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import type {FooterContentData, FooterContentResponse} from '@/features/layout/api';
import {Footer} from '@/features/layout/components/Footer/Footer';
import {
  LayoutContext,
  type LayoutContextValue,
} from '@/features/layout/components/LayoutProvider/context';

vi.mock('@/components/SafeHtml/SafeHtml', () => ({
  SafeHtml: ({html, className}: {html: string; className?: string}) => (
    <div data-testid="safe-html" className={className}>
      {html}
    </div>
  ),
}));

afterEach(() => {
  cleanup();
});

const makeFooter = (content: FooterContentData = {}): FooterContentResponse => ({
  id: 'footer-id',
  name: 'Footer',
  slug: 'footer',
  content,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
});

const renderFooter = (overrides: Partial<LayoutContextValue> = {}) => {
  const value: LayoutContextValue = {
    state: 'ready',
    menus: [],
    footer: null,
    error: null,
    ...overrides,
  };
  return render(
    <LayoutContext.Provider value={value}>
      <Footer />
    </LayoutContext.Provider>,
  );
};

describe('Footer', () => {
  it('renders the footer bottom with copyright and footer links', () => {
    renderFooter({
      footer: makeFooter({
        copyright: '© 2026 UC Merced',
        footer_links: [{label: 'Privacy', href: '/privacy'}],
      }),
    });

    expect(screen.getByText('© 2026 UC Merced')).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'Privacy'})).toHaveAttribute(
      'href',
      '/privacy',
    );
  });

  it('omits the footer bottom when there is no copyright or footer links', () => {
    const {container} = renderFooter({footer: makeFooter()});
    expect(container.querySelector('.footer-bottom')).toBeNull();
  });

  it('omits the contact block when there is no contact HTML', () => {
    renderFooter({
      footer: makeFooter({
        cta_buttons: [{label: 'Go', href: '/go'}],
      }),
    });

    expect(screen.getByRole('link', {name: 'Go'})).toBeInTheDocument();
    expect(screen.queryByTestId('safe-html')).toBeNull();
  });

  it('names social links from the icon class when no label is provided', () => {
    renderFooter({
      footer: makeFooter({
        columns: [{title: 'Connect'}],
        social_links: [
          {href: 'https://x.com', icon_class: 'fa fa-twitter'},
          {href: 'https://example.com/feed', icon_class: ''},
        ],
      }),
    });

    const twitter = screen.getByRole('link', {name: 'Twitter'});
    expect(twitter).toHaveAttribute('href', 'https://x.com');
    expect(twitter).not.toHaveAttribute('aria-label');
    expect(screen.getByRole('link', {name: 'https://example.com/feed'})).toBeInTheDocument();
  });

  it('sanitizes unsafe hrefs via safeHref', () => {
    renderFooter({
      footer: makeFooter({
        footer_links: [{label: 'Danger', href: 'javascript:alert(1)'}],
      }),
    });

    expect(screen.getByRole('link', {name: 'Danger'})).toHaveAttribute(
      'href',
      '#',
    );
  });

  it('renders the copyright bar as one list with the copyright first', () => {
    const {container} = renderFooter({
      footer: makeFooter({
        copyright: '© 2026',
        footer_links: [
          {label: 'Directions', href: 'https://example.com/directions', target: '_blank', rel: 'noopener'},
        ],
      }),
    });

    const meta = container.querySelector('.footer-bottom .footer-meta') as HTMLElement;
    expect(within(meta).getAllByRole('listitem').map((item) => item.textContent)).toEqual(['© 2026', 'Directions']);
    expect(within(meta).getByRole('link', {name: 'Directions'})).toHaveAttribute('target', '_blank');
  });

  it('keeps a social link without a known icon as a text link', () => {
    renderFooter({
      footer: makeFooter({
        columns: [{title: 'Contact', body_html: '<p>Address</p>'}],
        social_links: [{href: 'https://example.com/feed', icon_class: ''}],
      }),
    });

    const link = screen.getByRole('link', {name: 'https://example.com/feed'});
    expect(link).toHaveClass('footer-social-link', 'is-text');
    expect(link.querySelector('svg')).toBeNull();
  });

  it('shows the contact line under the CTA row even without buttons', () => {
    renderFooter({
      footer: makeFooter({contact_html: '<p>For any questions, email us.</p>'}),
    });

    expect(screen.getByTestId('safe-html')).toHaveClass('site-footer-cta-contact');
    expect(screen.queryByRole('list')).toBeNull();
  });
});
