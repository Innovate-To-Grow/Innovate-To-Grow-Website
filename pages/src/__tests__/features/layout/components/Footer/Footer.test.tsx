import {cleanup, render, screen} from '@testing-library/react';
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

vi.mock('@/components/Icon/Icon', () => ({
  Icon: ({name, className}: {name: string; className?: string}) => (
    <svg data-icon-name={name} className={className} />
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
  it('renders nothing while loading', () => {
    const {container} = renderFooter({state: 'loading'});
    expect(container).toBeEmptyDOMElement();
  });

  it('shows a fallback error message when the layout fails', () => {
    renderFooter({state: 'error'});
    expect(screen.getByRole('status')).toHaveTextContent(
      'Footer is currently unavailable.',
    );
  });

  it('shows the specific error message when one is provided', () => {
    renderFooter({state: 'ready', error: 'Down for maintenance'});
    expect(screen.getByRole('status')).toHaveTextContent(
      'Down for maintenance',
    );
  });

  it('renders nothing when there is no footer content', () => {
    const {container} = renderFooter({state: 'ready', footer: null});
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the footer landmark', () => {
    renderFooter({footer: makeFooter()});
    expect(screen.getByRole('contentinfo')).toBeInTheDocument();
  });

  it('renders CTA buttons with the correct colors and the contact block', () => {
    renderFooter({
      footer: makeFooter({
        cta_buttons: [
          {label: 'Get Started', href: '/start', style: 'gold'},
          {label: 'Learn More', href: '/learn', style: 'blue'},
          {label: 'Default', href: '/def'},
        ],
        contact_html: '<p>Contact us</p>',
      }),
    });

    const gold = screen.getByRole('link', {name: 'Get Started'});
    expect(gold).toHaveAttribute('href', '/start');
    expect(gold.parentElement).toHaveClass('hb__buttons-gold');

    const blue = screen.getByRole('link', {name: 'Learn More'});
    expect(blue.parentElement).toHaveClass('hb__buttons-blue');

    const def = screen.getByRole('link', {name: 'Default'});
    expect(def.parentElement).toHaveClass('hb__buttons-blue');

    expect(screen.getByTestId('safe-html')).toHaveTextContent('Contact us');
  });

  it('renders columns with titles, links, body html, and address social icons', () => {
    renderFooter({
      footer: makeFooter({
        columns: [
          {
            title: 'Explore',
            links: [
              {
                label: 'Projects',
                href: 'https://example.com/projects',
                target: '_blank',
                rel: 'noopener',
              },
            ],
          },
          {title: 'Contact', body_html: '<p>Address here</p>'},
        ],
        social_links: [
          {href: 'https://facebook.com', icon_class: 'fa-facebook', aria_label: 'Facebook'},
        ],
      }),
    });

    expect(screen.getByRole('heading', {name: 'Explore'})).toBeInTheDocument();

    const link = screen.getByRole('link', {name: 'Projects'});
    expect(link).toHaveAttribute('href', 'https://example.com/projects');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener');

    const bodies = screen.getAllByTestId('safe-html');
    expect(
      bodies.some((el) => (el.textContent ?? '').includes('Address here')),
    ).toBe(true);

    const social = document.querySelector('svg[data-icon-name="fa-facebook"]');
    expect(social).not.toBeNull();
    expect(screen.getByRole('link', {name: 'Facebook'})).toHaveAttribute(
      'href',
      'https://facebook.com',
    );
  });

  it('renders a column without a title or links', () => {
    renderFooter({
      footer: makeFooter({columns: [{body_html: '<p>Body only</p>'}]}),
    });

    expect(screen.queryByRole('heading')).toBeNull();
    expect(screen.getByTestId('safe-html')).toHaveTextContent('Body only');
  });

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

  it('omits the aria-label on social links that do not provide one', () => {
    renderFooter({
      footer: makeFooter({
        columns: [{title: 'Connect'}],
        social_links: [{href: 'https://x.com', icon_class: 'fa-x'}],
      }),
    });

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', 'https://x.com');
    expect(link).not.toHaveAttribute('aria-label');
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
});
