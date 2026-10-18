import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {FaqListBlock} from '@/features/cms/components/blocks/content/FaqListBlock';

describe('FaqListBlock', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the section wrapper and a heading when provided', () => {
    const {container} = render(
      <FaqListBlock data={{heading: 'FAQ', items: []}} />,
    );
    expect(container.querySelector('.cms-faq-list')).not.toBeNull();
    expect(screen.getByRole('heading', {name: 'FAQ', level: 1})).toHaveClass(
      'itg-page-title',
      'cms-page-title',
    );
  });

  it('omits the heading when not provided', () => {
    render(<FaqListBlock data={{items: []}} />);
    expect(screen.queryByRole('heading')).toBeNull();
  });

  it('renders each question as an h2 and its sanitized answer HTML', () => {
    render(
      <FaqListBlock
        data={{
          items: [
            {question: 'What is I2G?', answer_html: '<p>Innovate To Grow</p>'},
            {question: 'Who can apply?', answer_html: '<p>UC Merced students</p>'},
          ],
        }}
      />,
    );

    expect(
      screen.getByRole('heading', {name: 'What is I2G?', level: 2}),
    ).toBeInTheDocument();
    expect(screen.getByText('Innovate To Grow')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', {name: 'Who can apply?', level: 2}),
    ).toBeInTheDocument();
    expect(screen.getByText('UC Merced students')).toBeInTheDocument();
  });

  it('styles questions as section titles and answers as prose', () => {
    const {container} = render(
      <FaqListBlock
        data={{items: [{question: 'What is I2G?', answer_html: '<p>Innovate To Grow</p>'}]}}
      />,
    );

    expect(screen.getByRole('heading', {name: 'What is I2G?', level: 2})).toHaveClass(
      'itg-section-title',
      'cms-faq-question',
    );
    expect(container.querySelector('.cms-faq-answer')).toHaveClass('cms-prose');
  });

  it('renders no questions when items are malformed', () => {
    const {container} = render(
      <FaqListBlock data={{heading: 'FAQ', items: undefined as unknown as []}} />,
    );
    expect(container.querySelectorAll('.cms-faq-item')).toHaveLength(0);
  });
});
