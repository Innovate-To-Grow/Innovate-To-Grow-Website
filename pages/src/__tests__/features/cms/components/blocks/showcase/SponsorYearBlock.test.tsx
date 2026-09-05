import {cleanup, render} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {SponsorYearBlock} from '@/features/cms/components/blocks/showcase/SponsorYearBlock';

describe('SponsorYearBlock', () => {
  afterEach(() => {
    cleanup();
  });

  it('returns null when the year is missing', () => {
    const {container} = render(
      <SponsorYearBlock data={{year: '', sponsors: [{name: 'Acme'}]}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('returns null when there are no sponsors', () => {
    const {container} = render(<SponsorYearBlock data={{year: '2025', sponsors: []}} />);
    expect(container.firstChild).toBeNull();
  });

  it('returns null when sponsors is not an array', () => {
    const {container} = render(
      <SponsorYearBlock data={{year: '2025', sponsors: 'nope' as unknown as []}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('returns null when data is missing', () => {
    const {container} = render(
      <SponsorYearBlock data={undefined as unknown as {year: string; sponsors: []}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the year title', () => {
    const {container} = render(
      <SponsorYearBlock data={{year: ' 2025 ', sponsors: [{name: 'Acme'}]}} />,
    );
    expect(container.querySelector('h2.cms-sponsor-year-title')?.textContent).toBe(
      '2025 Sponsors',
    );
  });

  it('renders a logo image when logo_url is provided', () => {
    const {container} = render(
      <SponsorYearBlock
        data={{
          year: '2025',
          sponsors: [{name: 'Acme', logo_url: ' https://example.com/logo.png '}],
        }}
      />,
    );
    const img = container.querySelector('img.cms-sponsor-logo');
    expect(img?.getAttribute('src')).toBe('https://example.com/logo.png');
    expect(img?.getAttribute('alt')).toBe('Acme');
    expect(img?.getAttribute('loading')).toBe('lazy');
  });

  it('renders a placeholder with the uppercased first letter when logo_url is absent', () => {
    const {container} = render(
      <SponsorYearBlock data={{year: '2025', sponsors: [{name: 'acme'}]}} />,
    );
    const placeholder = container.querySelector('.cms-sponsor-card-placeholder');
    expect(placeholder?.textContent).toBe('A');
    expect(placeholder).toHaveAttribute('aria-hidden', 'true');
    expect(container.querySelector('img.cms-sponsor-logo')).toBeNull();
  });

  it('wraps a sponsor with a website in a sanitized external link', () => {
    const {container} = render(
      <SponsorYearBlock
        data={{
          year: '2025',
          sponsors: [{name: 'Acme', website: 'https://acme.example '}],
        }}
      />,
    );
    const link = container.querySelector('a.cms-sponsor-card');
    expect(link?.getAttribute('href')).toBe('https://acme.example');
    expect(link?.getAttribute('target')).toBe('_blank');
    expect(link?.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('renders a non-linking card when the sponsor has no website', () => {
    const {container} = render(
      <SponsorYearBlock data={{year: '2025', sponsors: [{name: 'Acme'}]}} />,
    );
    expect(container.querySelector('a.cms-sponsor-card')).toBeNull();
    expect(container.querySelector('div.cms-sponsor-card')).not.toBeNull();
  });

  it('renders the sponsor name next to the logo/placeholder', () => {
    const {container} = render(
      <SponsorYearBlock data={{year: '2025', sponsors: [{name: 'Acme'}]}} />,
    );
    expect(container.querySelector('.cms-sponsor-name')?.textContent).toBe('Acme');
  });

  it('skips invalid sponsor entries during normalization', () => {
    const {container} = render(
      <SponsorYearBlock
        data={{
          year: '2025',
          sponsors: [
            null,
            undefined,
            'just-a-string',
            42,
            {name: ''},
            {name: '   '},
            {name: 123},
            {name: 'Valid'},
          ] as unknown as [],
        }}
      />,
    );
    const names = container.querySelectorAll('.cms-sponsor-name');
    expect(names).toHaveLength(1);
    expect(names[0].textContent).toBe('Valid');
  });
});
