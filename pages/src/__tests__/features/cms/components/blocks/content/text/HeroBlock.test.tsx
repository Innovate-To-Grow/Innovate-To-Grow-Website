import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {HeroBlock} from '@/features/cms/components/blocks/content/HeroBlock';

describe('HeroBlock', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the heading as the page title followed by the subheading as the lead', () => {
    const {container} = render(
      <HeroBlock data={{heading: 'Innovate to Grow', subheading: 'Students and partners solving real problems.'}} />,
    );
    const title = screen.getByRole('heading', {name: 'Innovate to Grow', level: 1});
    expect(title).toHaveClass('itg-page-title', 'cms-hero-title');
    // The lead (the theme's .lead) carries the navy rule; the title is never ruled.
    expect(title).not.toHaveClass('itg-page-title-ruled');
    const lead = container.querySelector('p.itg-lead');
    expect(lead).toHaveTextContent('Students and partners solving real problems.');
    expect(title.nextElementSibling).toBe(lead);
  });

  it('gives a title without a lead the CMS page-title spacing and no rule', () => {
    const {container} = render(<HeroBlock data={{heading: 'Events'}} />);
    const title = screen.getByRole('heading', {name: 'Events', level: 1});
    expect(title).toHaveClass('itg-page-title', 'cms-page-title');
    expect(title).not.toHaveClass('itg-page-title-ruled');
    expect(container.querySelector('.itg-lead')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
  });

  it('renders the image in the main column after the title, with its alt text and local variants', () => {
    const {container} = render(
      <HeroBlock
        data={{
          heading: 'Showcase',
          subheading: 'Lead',
          image_url: '/assets/images/home_img.jpg',
          image_alt: 'Students at the showcase',
        }}
      />,
    );
    const img = screen.getByAltText('Students at the showcase');
    expect(img).toHaveClass('cms-hero-image');
    expect(img).toHaveAttribute('src', '/assets/images/home-img-1600.webp');
    expect(img.getAttribute('srcset')).toContain('home-img-800.webp 800w');
    expect(img).toHaveAttribute('width', '1600');
    expect(img).toHaveAttribute('loading', 'lazy');
    expect(img).not.toHaveAttribute('fetchpriority');
    expect(container.querySelector('.cms-hero')?.lastElementChild).toBe(img);
    // No full-bleed band: nothing but the title, lead and image.
    expect(container.querySelector('.cms-hero')?.children).toHaveLength(3);
  });

  it('keeps remote images as-is, defaults alt to empty and loads a priority image eagerly', () => {
    render(<HeroBlock priority data={{image_url: 'https://example.com/banner.jpg'}} />);
    const img = document.querySelector('img.cms-hero-image');
    expect(img).toHaveAttribute('src', 'https://example.com/banner.jpg');
    expect(img).not.toHaveAttribute('srcset');
    expect(img).toHaveAttribute('alt', '');
    expect(img).toHaveAttribute('loading', 'eager');
    expect(img).toHaveAttribute('fetchpriority', 'high');
  });

  it('renders nothing when every field is empty (the schema has no required fields)', () => {
    const {container} = render(<HeroBlock data={{heading: '  ', subheading: '', image_url: ''}} />);
    expect(container).toBeEmptyDOMElement();
  });
});
