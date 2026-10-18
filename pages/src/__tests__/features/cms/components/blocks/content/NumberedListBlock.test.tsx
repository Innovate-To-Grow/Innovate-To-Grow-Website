import {cleanup, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {NumberedListBlock} from '@/features/cms/components/blocks/content/NumberedListBlock';

describe('NumberedListBlock', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the heading, the preamble and an ordered list inside the prose wrapper', () => {
    const {container} = render(
      <NumberedListBlock
        data={{
          heading: 'How to submit',
          preamble_html: '<p>Follow these steps:</p>',
          items: ['Read the sample proposals.', 'Fill in the form.', 'Wait for the email.'],
        }}
      />,
    );
    expect(screen.getByRole('heading', {name: 'How to submit', level: 2})).toHaveClass(
      'section-title',
      'itg-section-title',
    );
    const body = container.querySelector('.cms-numbered-list-body');
    expect(body).toHaveClass('cms-prose');
    const preamble = body?.querySelector('.cms-numbered-list-preamble');
    expect(preamble).toHaveTextContent('Follow these steps:');

    const list = screen.getByRole('list');
    expect(list.tagName).toBe('OL');
    expect(list).toHaveClass('cms-numbered-list-items');
    expect(preamble?.nextElementSibling).toBe(list);
    expect(within(list).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'Read the sample proposals.',
      'Fill in the form.',
      'Wait for the email.',
    ]);
  });

  it('renders items as plain text, never as HTML', () => {
    const {container} = render(<NumberedListBlock data={{items: ['<b>bold</b> <img src=x onerror=alert(1)>']}} />);
    expect(container.querySelector('b')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByRole('listitem')).toHaveTextContent('<b>bold</b> <img src=x onerror=alert(1)>');
  });

  it('sanitizes the preamble HTML', () => {
    const {container} = render(
      <NumberedListBlock
        data={{preamble_html: '<p>Intro<script>alert(1)</script></p><a href="javascript:alert(2)">x</a>', items: ['One']}}
      />,
    );
    expect(screen.getByText('Intro')).toBeInTheDocument();
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('a')?.getAttribute('href') ?? '').not.toContain('javascript:');
  });

  it('drops blank and non-text items and omits empty parts', () => {
    const {container} = render(
      <NumberedListBlock data={{items: ['First', '', '  ', 2, null, {text: 'object'}] as unknown as string[]}} />,
    );
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual(['First', '2']);
    expect(container.querySelector('.cms-numbered-list-preamble')).toBeNull();
    expect(screen.queryByRole('heading')).toBeNull();
  });

  it('renders no list when there are no items', () => {
    render(<NumberedListBlock data={{heading: 'Steps', preamble_html: '<p>Coming soon.</p>', items: []}} />);
    expect(screen.queryByRole('list')).toBeNull();
    expect(screen.getByText('Coming soon.')).toBeInTheDocument();
  });
});
