import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {SectionGroupBlock} from '@/features/cms/components/blocks/navigation/SectionGroupBlock';

describe('SectionGroupBlock', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the group wrapper and a top-level heading when provided', () => {
    const {container} = render(
      <SectionGroupBlock data={{heading: 'Resources', sections: []}} />,
    );
    expect(container.querySelector('.cms-section-group')).not.toBeNull();
    expect(screen.getByRole('heading', {name: 'Resources', level: 1})).toHaveClass(
      'section-title',
    );
  });

  it('omits the top-level heading when not provided', () => {
    const {container} = render(<SectionGroupBlock data={{sections: []}} />);
    expect(container.querySelector('h1')).toBeNull();
  });

  it('renders each section with a default h2 heading and sanitized body', () => {
    render(
      <SectionGroupBlock
        data={{
          sections: [
            {heading: 'Overview', body_html: '<p>Intro</p>'},
            {heading: 'Details', body_html: '<p>More</p>'},
          ],
        }}
      />,
    );

    expect(screen.getByRole('heading', {name: 'Overview', level: 2})).toHaveClass(
      'section-title',
    );
    expect(screen.getByText('Intro')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Details', level: 2})).toHaveClass(
      'section-title',
    );
    expect(screen.getByText('More')).toBeInTheDocument();
  });

  it('honors a per-section heading_level', () => {
    render(
      <SectionGroupBlock
        data={{sections: [{heading: 'Deep Dive', heading_level: 3, body_html: ''}]}}
      />,
    );
    expect(screen.getByRole('heading', {name: 'Deep Dive', level: 3})).toBeInTheDocument();
  });

  it('falls back to h2 when a section heading_level is falsy', () => {
    render(
      <SectionGroupBlock
        data={{sections: [{heading: 'Overview', heading_level: 0, body_html: ''}]}}
      />,
    );
    expect(screen.getByRole('heading', {name: 'Overview', level: 2})).toBeInTheDocument();
  });
});
