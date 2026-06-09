import {render, screen} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {Footer} from '@/features/layout/components/Footer/Footer';
import type {FooterContentResponse} from '@/features/layout/api';

const footerMocks = vi.hoisted(() => ({
  hookValue: {
    footer: null as FooterContentResponse | null,
    state: 'loading' as const,
    error: null as string | null,
  },
}));

vi.mock('@/features/layout/components/LayoutProvider/context', () => ({
  useFooter: () => footerMocks.hookValue,
}));

const footerContent: FooterContentResponse = {
  id: 'footer',
  name: 'Footer',
  slug: 'footer',
  is_active: true,
  created_at: '',
  updated_at: '',
  content: {
    cta_buttons: [
      {label: 'Register', href: '/event-registration', style: 'gold'},
      {label: 'Projects', href: '/projects', style: 'blue'},
    ],
    contact_html: '<p>Contact <strong>I2G</strong></p>',
    columns: [
      {
        title: 'Explore',
        links: [{label: 'Current Projects', href: '/projects'}],
      },
      {
        title: 'Address',
        body_html: '<p>5200 Lake Road</p>',
      },
    ],
    social_links: [
      {
        href: 'https://example.com',
        icon_class: 'fa fa-linkedin',
        aria_label: 'LinkedIn',
        target: '_blank',
        rel: 'noopener noreferrer',
      },
    ],
    copyright: 'Copyright 2026',
    footer_links: [{label: 'Privacy', href: 'javascript:alert(1)'}],
  },
};

describe('Footer', () => {
  beforeEach(() => {
    footerMocks.hookValue = {
      footer: null,
      state: 'loading',
      error: null,
    };
  });

  it('renders nothing while loading and a status message for errors', () => {
    const {container, rerender} = render(<Footer />);

    expect(container).toBeEmptyDOMElement();

    footerMocks.hookValue = {
      footer: null,
      state: 'error',
      error: 'Footer failed',
    };
    rerender(<Footer />);

    expect(screen.getByRole('status')).toHaveTextContent('Footer failed');
  });

  it('renders CTA buttons, footer columns, social links, and sanitized footer links', () => {
    footerMocks.hookValue = {
      footer: footerContent,
      state: 'ready',
      error: null,
    };

    render(<Footer />);

    expect(screen.getByRole('link', {name: 'Register'})).toHaveAttribute('href', '/event-registration');
    expect(screen.getByRole('link', {name: 'Projects'})).toHaveAttribute('href', '/projects');
    expect(screen.getByText('Explore')).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'Current Projects'})).toHaveAttribute('href', '/projects');
    expect(screen.getByText('5200 Lake Road')).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'LinkedIn'})).toHaveAttribute('target', '_blank');
    expect(screen.getByText('Copyright 2026')).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'Privacy'})).toHaveAttribute('href', '#');
  });
});
