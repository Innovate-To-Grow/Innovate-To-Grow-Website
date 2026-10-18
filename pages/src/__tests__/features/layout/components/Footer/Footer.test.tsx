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
    expect(gold).toHaveClass('site-footer-cta-link', 'is-gold');

    const blue = screen.getByRole('link', {name: 'Learn More'});
    expect(blue).toHaveClass('site-footer-cta-link', 'is-blue');

    const def = screen.getByRole('link', {name: 'Default'});
    expect(def).toHaveClass('is-blue');

    // The CTA row is part of the footer landmark, as a list of links.
    const footer = screen.getByRole('contentinfo');
    expect(within(footer).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'Get Started',
      'Learn More',
      'Default',
    ]);
    expect(screen.getByTestId('safe-html')).toHaveTextContent('Contact us');
  });

  it('renders columns with titles, links, body html, and address social links', () => {
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

    // Social links are text links in the last (contact) column.
    const contact = screen.getByRole('heading', {name: 'Contact'}).parentElement as HTMLElement;
    expect(contact).toHaveClass('footer-column--address');
    expect(within(contact).getByRole('link', {name: 'Facebook'})).toHaveAttribute(
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

  it('styles the footer as the reference: centred columns, an address block without a visible heading, round social icons', () => {
    const {container} = renderFooter({
      footer: makeFooter({
        columns: [
          {title: 'Academics', links: [{label: 'School of Engineering', href: 'https://engineering.example'}]},
          {title: 'Contact', body_html: '<p>5200 North Lake Rd.</p>'},
        ],
        social_links: [
          {href: 'https://facebook.com', icon_class: 'fa fa-facebook', aria_label: 'Facebook'},
          {href: 'https://twitter.com/ucmerced', icon_class: 'fa fa-twitter', aria_label: 'Twitter'},
        ],
      }),
    });

    // Every column is a plain block (no phone accordions): stacked and centred by the sheet.
    expect(container.querySelector('details')).toBeNull();
    expect(screen.getByRole('heading', {name: 'Academics'})).toHaveClass('footer-column-title');
    expect(screen.getByRole('link', {name: 'School of Engineering'})).toHaveAttribute('href', 'https://engineering.example');

    // The contact heading stays in the outline but is visually hidden, as on the reference.
    expect(screen.getByRole('heading', {name: 'Contact'})).toHaveClass('sr-only');

    // Social links are round icons whose names stay readable to screen readers.
    const facebook = screen.getByRole('link', {name: 'Facebook'});
    expect(facebook).toHaveClass('footer-social-link');
    expect(facebook.querySelector('svg')).not.toBeNull();
    expect(facebook.querySelector('.sr-only')).toHaveTextContent('Facebook');
    expect(screen.getByRole('link', {name: 'Twitter'}).querySelector('svg')).not.toBeNull();
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
