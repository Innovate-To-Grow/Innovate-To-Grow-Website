import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {ImageTextBlock} from '@/features/cms/components/blocks/content/ImageTextBlock';

describe('ImageTextBlock', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the heading as the page title and the body as prose', () => {
    const {container} = render(
      <ImageTextBlock data={{heading: 'Engineering Capstone', body_html: '<p>Body copy</p>'}} />,
    );
    expect(screen.getByRole('heading', {name: 'Engineering Capstone', level: 1})).toHaveClass(
      'section-title',
      'itg-page-title',
      'cms-page-title',
    );
    expect(container.querySelector('.cms-image-text-body')).toHaveClass('cms-prose');
    expect(screen.getByText('Body copy')).toBeInTheDocument();
  });

  it('omits the heading and image when not provided', () => {
    const {container} = render(<ImageTextBlock data={{body_html: '<p>Only text</p>'}} />);
    expect(screen.queryByRole('heading')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
  });

  it('serves responsive local variants for known images and lazy-loads by default', () => {
    render(
      <ImageTextBlock
        data={{
          image_url: '/assets/about/engineering_capstone.webp',
          image_alt: 'Students at work',
          body_html: '',
        }}
      />,
    );
    const img = screen.getByAltText('Students at work');
    expect(img).toHaveAttribute('src', '/assets/images/engineering-capstone-1280.webp');
    expect(img.getAttribute('srcset')).toContain('engineering-capstone-640.webp 640w');
    expect(img).toHaveAttribute('loading', 'lazy');
    expect(img).toHaveClass('capstone-hero-image');
  });

  it('loads a priority image eagerly and keeps remote images as-is', () => {
    render(
      <ImageTextBlock
        priority
        data={{image_url: 'https://example.com/photo.jpg', body_html: ''}}
      />,
    );
    const img = document.querySelector('img.capstone-hero-image');
    expect(img).toHaveAttribute('src', 'https://example.com/photo.jpg');
    expect(img).toHaveAttribute('loading', 'eager');
    expect(img).toHaveAttribute('fetchpriority', 'high');
    expect(img).toHaveAttribute('alt', '');
  });

  it('keeps the image a direct child of the positioned content box', () => {
    // The 'left' two-column layout in the CMS sheet keys off
    // `.cms-image-text--left:has(> .capstone-hero-image)`, and 'right' floats
    // the same element, so the image must stay a direct child of that box.
    const {container} = render(
      <ImageTextBlock
        data={{image_position: 'left', image_url: '/photo.jpg', image_alt: 'Team', body_html: '<p>Text</p>'}}
      />,
    );
    const content = container.querySelector('.capstone-content');
    expect(content).toHaveClass('cms-image-text-content', 'cms-image-text--left');
    expect(content?.querySelector(':scope > img.capstone-hero-image')).not.toBeNull();
    expect(content?.querySelector(':scope > .cms-image-text-body')).toHaveClass('cms-prose');
    expect(content?.firstElementChild?.tagName).toBe('IMG');
  });

  it('applies the image position as a modifier class, defaulting to right', () => {
    const {container} = render(
      <ImageTextBlock data={{image_position: 'top', body_html: ''}} />,
    );
    expect(container.querySelector('.capstone-content')).toHaveClass('cms-image-text--top');

    const {container: fallback} = render(
      <ImageTextBlock data={{image_position: 'middle' as unknown as 'top', body_html: ''}} />,
    );
    expect(fallback.querySelector('.capstone-content')).toHaveClass('cms-image-text--right');
  });
});
