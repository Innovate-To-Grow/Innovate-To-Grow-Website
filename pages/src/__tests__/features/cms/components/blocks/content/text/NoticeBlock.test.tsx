import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {NoticeBlock, type NoticeStyle} from '@/features/cms/components/blocks/content/NoticeBlock';

describe('NoticeBlock', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders an info notice as the global notice box with a heading and prose body', () => {
    const {container} = render(
      <NoticeBlock data={{heading: 'Heads up', style: 'info', body_html: '<p>Registration opens in May.</p>'}} />,
    );
    const note = screen.getByRole('note');
    expect(note).toHaveClass('cms-notice', 'cms-notice--info', 'itg-notice');
    expect(note).not.toHaveClass('itg-notice-warning');
    expect(screen.getByRole('heading', {name: 'Heads up', level: 2})).toHaveClass('cms-notice-title');
    expect(container.querySelector('.cms-notice-body')).toHaveClass('cms-prose');
    expect(screen.getByText('Registration opens in May.')).toBeInTheDocument();
  });

  it.each([
    ['warning', 'itg-notice-warning'],
    ['success', 'itg-notice-success'],
  ] as const)('maps the %s style to the %s variant', (style, variantClass) => {
    render(<NoticeBlock data={{style, body_html: '<p>Body</p>'}} />);
    expect(screen.getByRole('note')).toHaveClass('itg-notice', variantClass, `cms-notice--${style}`);
  });

  it('treats a missing or unknown style as info', () => {
    render(<NoticeBlock data={{body_html: '<p>Default</p>'}} />);
    expect(screen.getByRole('note')).toHaveClass('itg-notice', 'cms-notice--info');
    cleanup();

    for (const style of ['danger', 'constructor', 'WARNING ']) {
      render(<NoticeBlock data={{style: style as NoticeStyle, body_html: '<p>x</p>'}} />);
      const note = screen.getByRole('note');
      if (style === 'WARNING ') {
        expect(note).toHaveClass('itg-notice-warning');
      } else {
        expect(note).toHaveClass('cms-notice--info');
        expect(note.className).not.toMatch(/undefined|function/);
      }
      cleanup();
    }
  });

  it('omits the heading when not provided', () => {
    render(<NoticeBlock data={{style: 'success', body_html: '<p>Saved.</p>'}} />);
    expect(screen.queryByRole('heading')).toBeNull();
  });

  it('sanitizes the body HTML', () => {
    const {container} = render(
      <NoticeBlock
        data={{body_html: '<p>Safe<img src="x" onerror="alert(1)"></p><script>alert(2)</script>'}}
      />,
    );
    expect(screen.getByText('Safe')).toBeInTheDocument();
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')?.getAttribute('onerror')).toBeNull();
  });
});
