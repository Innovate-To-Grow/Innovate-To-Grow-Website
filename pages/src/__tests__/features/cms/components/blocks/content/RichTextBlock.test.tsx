import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {RichTextBlock} from '@/features/cms/components/blocks/content/RichTextBlock';

describe('RichTextBlock', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders body HTML through SafeHtml inside the prose wrapper', () => {
    const {container} = render(<RichTextBlock data={{body_html: '<p>Hello world</p>'}} />);
    expect(screen.getByText('Hello world')).toBeInTheDocument();
    expect(container.querySelector('.cms-rich-text-body')).toHaveClass('cms-prose');
  });

  it('defaults the heading to h2 with the section-title classes', () => {
    render(<RichTextBlock data={{heading: 'About', body_html: ''}} />);
    expect(screen.getByRole('heading', {name: 'About', level: 2})).toHaveClass(
      'section-title',
      'itg-section-title',
    );
  });

  it('honors a custom heading_level', () => {
    render(
      <RichTextBlock data={{heading: 'About', heading_level: 3, body_html: ''}} />,
    );
    expect(screen.getByRole('heading', {name: 'About', level: 3})).toHaveClass(
      'section-title',
      'itg-subsection-title',
    );
  });

  it('renders a level-1 heading as the page title, including string levels', () => {
    render(
      <RichTextBlock
        data={{heading: 'Project Submission', heading_level: '1' as unknown as number, body_html: ''}}
      />,
    );
    expect(screen.getByRole('heading', {name: 'Project Submission', level: 1})).toHaveClass(
      'section-title',
      'itg-page-title',
      'cms-page-title',
    );
  });

  it('falls back to h2 when heading_level is falsy', () => {
    render(
      <RichTextBlock data={{heading: 'About', heading_level: 0, body_html: ''}} />,
    );
    expect(screen.getByRole('heading', {name: 'About', level: 2})).toBeInTheDocument();
  });

  it('falls back to h2 when heading_level is out of range', () => {
    render(
      <RichTextBlock data={{heading: 'About', heading_level: 9, body_html: ''}} />,
    );
    expect(screen.getByRole('heading', {name: 'About', level: 2})).toBeInTheDocument();
  });

  it('omits the heading when not provided', () => {
    render(<RichTextBlock data={{body_html: ''}} />);
    expect(screen.queryByRole('heading')).toBeNull();
  });
});
