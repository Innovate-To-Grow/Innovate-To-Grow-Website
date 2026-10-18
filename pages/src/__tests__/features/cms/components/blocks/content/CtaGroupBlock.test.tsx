import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, describe, expect, it} from 'vitest';

import {CtaGroupBlock, type CtaItem} from '@/features/cms/components/blocks/content/CtaGroupBlock';

function renderItems(items: CtaItem[]) {
  return render(
    <MemoryRouter>
      <CtaGroupBlock data={{items}} />
    </MemoryRouter>,
  );
}

describe('CtaGroupBlock', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders a list of design-system button links', () => {
    const {container} = renderItems([
      {label: 'Register', href: '/event-registration', style: 'primary'},
      {label: 'Sample proposals', href: '/sample-proposals', style: 'secondary'},
    ]);
    const list = container.querySelector('ul.cms-cta-group-list');
    expect(list?.querySelectorAll(':scope > li.cms-cta-group-item')).toHaveLength(2);
    const register = screen.getByRole('link', {name: 'Register'});
    expect(register).toHaveClass('itg-btn', 'itg-btn-primary', 'cms-cta-group-button');
    expect(register).toHaveAttribute('href', '/event-registration');
    expect(register).not.toHaveAttribute('target');
    expect(screen.getByRole('link', {name: 'Sample proposals'})).toHaveClass('itg-btn', 'itg-btn-outline');
  });

  it('maps each editor style to a button variant, accepting btn- and itg-btn- prefixes', () => {
    renderItems([
      {label: 'Outline', href: '/a', style: 'outline'},
      {label: 'Accent', href: '/b', style: 'accent'},
      {label: 'Gold', href: '/c', style: ' Gold '},
      {label: 'Bright', href: '/d', style: 'bright'},
      {label: 'Text', href: '/e', style: 'text'},
      {label: 'Link', href: '/f', style: 'link'},
      {label: 'Prefixed', href: '/g', style: 'btn-primary'},
      {label: 'Class name', href: '/h', style: 'itg-btn-secondary'},
    ]);
    expect(screen.getByRole('link', {name: 'Outline'})).toHaveClass('itg-btn-outline');
    expect(screen.getByRole('link', {name: 'Accent'})).toHaveClass('itg-btn-accent');
    expect(screen.getByRole('link', {name: 'Gold'})).toHaveClass('itg-btn-accent');
    expect(screen.getByRole('link', {name: 'Bright'})).toHaveClass('itg-btn-bright');
    expect(screen.getByRole('link', {name: 'Text'})).toHaveClass('itg-btn-text');
    expect(screen.getByRole('link', {name: 'Link'})).toHaveClass('itg-btn-text');
    expect(screen.getByRole('link', {name: 'Prefixed'})).toHaveClass('itg-btn-primary');
    expect(screen.getByRole('link', {name: 'Class name'})).toHaveClass('itg-btn-outline');
  });

  it('makes the first unstyled button primary and the others outlined', () => {
    renderItems([
      {label: 'Main', href: '/main', style: ''},
      {label: 'Second', href: '/second'},
      {label: 'Unknown', href: '/third', style: 'constructor'},
    ]);
    expect(screen.getByRole('link', {name: 'Main'})).toHaveClass('itg-btn-primary');
    expect(screen.getByRole('link', {name: 'Second'})).toHaveClass('itg-btn-outline');
    expect(screen.getByRole('link', {name: 'Unknown'})).toHaveClass('itg-btn', 'itg-btn-outline');
  });

  it('opens other sites in a new tab and keeps mailto/tel links in place', () => {
    renderItems([
      {label: 'UC Merced', href: 'https://www.ucmerced.edu'},
      {label: 'Email us', href: 'mailto:i2g@ucmerced.edu', style: 'text'},
      {label: 'Call', href: 'tel:+12095550123'},
    ]);
    const external = screen.getByRole('link', {name: /^UC Merced\s*\(opens in a new tab\)$/});
    expect(external).toHaveAttribute('href', 'https://www.ucmerced.edu');
    expect(external).toHaveAttribute('target', '_blank');
    expect(external).toHaveAttribute('rel', 'noopener noreferrer');
    const email = screen.getByRole('link', {name: 'Email us'});
    expect(email).toHaveAttribute('href', 'mailto:i2g@ucmerced.edu');
    expect(email).not.toHaveAttribute('target');
    expect(screen.getByRole('link', {name: 'Call'})).toHaveAttribute('href', 'tel:+12095550123');
  });

  it('neutralises unsafe or protocol-relative hrefs', () => {
    renderItems([
      {label: 'Script', href: 'javascript:alert(1)'},
      {label: 'Data', href: 'data:text/html,<script>alert(1)</script>'},
      {label: 'Other origin', href: '//evil.example.com/path'},
    ]);
    for (const name of ['Script', 'Data', 'Other origin']) {
      const link = screen.getByRole('link', {name});
      expect(link).toHaveAttribute('href', '#');
      expect(link).not.toHaveAttribute('target');
    }
  });

  it('falls back to a url field and skips items without a label', () => {
    renderItems([
      {label: 'Legacy shape', url: '/schedule'},
      {label: '   ', href: '/hidden'},
      {href: '/no-label'} as unknown as CtaItem,
      null as unknown as CtaItem,
    ]);
    expect(screen.getAllByRole('link')).toHaveLength(1);
    expect(screen.getByRole('link', {name: 'Legacy shape'})).toHaveAttribute('href', '/schedule');
  });

  it('renders nothing without usable items', () => {
    const {container} = render(
      <MemoryRouter>
        <CtaGroupBlock data={{items: 'oops' as unknown as CtaItem[]}} />
      </MemoryRouter>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
