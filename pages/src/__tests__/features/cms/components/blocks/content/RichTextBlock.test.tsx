import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {RichTextBlock} from '@/features/cms/components/blocks/content/RichTextBlock';

describe('RichTextBlock', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders body HTML through SafeHtml', () => {
    render(<RichTextBlock data={{body_html: '<p>Hello world</p>'}} />);
    expect(screen.getByText('Hello world')).toBeInTheDocument();
  });

  it('defaults the heading to h2 with the section-title class', () => {
    render(<RichTextBlock data={{heading: 'About', body_html: ''}} />);
    expect(screen.getByRole('heading', {name: 'About', level: 2})).toHaveClass(
      'section-title',
    );
  });

  it('honors a custom heading_level', () => {
    render(
      <RichTextBlock data={{heading: 'About', heading_level: 3, body_html: ''}} />,
    );
    expect(screen.getByRole('heading', {name: 'About', level: 3})).toHaveClass(
      'section-title',
    );
  });

  it('falls back to h2 when heading_level is falsy', () => {
    render(
      <RichTextBlock data={{heading: 'About', heading_level: 0, body_html: ''}} />,
    );
    expect(screen.getByRole('heading', {name: 'About', level: 2})).toBeInTheDocument();
  });

  it('omits the heading when not provided', () => {
    render(<RichTextBlock data={{body_html: ''}} />);
    expect(screen.queryByRole('heading')).toBeNull();
  });
});
