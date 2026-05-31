import { describe, it, expect, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { FrozenPageBlock } from './FrozenPageBlock';

afterEach(() => cleanup());

describe('FrozenPageBlock', () => {
  it('renders a sandboxed iframe pointing at the frozen document', () => {
    const { container } = render(<FrozenPageBlock data={{ frozen_page_id: 'abc-123' }} />);
    const iframe = container.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute('src')).toBe('/api/cms/frozen/abc-123/');
    // sandbox="" — fully isolated (no scripts/forms/same-origin).
    expect(iframe?.getAttribute('sandbox')).toBe('');
    expect(iframe?.getAttribute('referrerpolicy')).toBe('no-referrer');
  });

  it('defaults to 600px and lazy loading outside preview', () => {
    const { container } = render(<FrozenPageBlock data={{ frozen_page_id: 'abc-123' }} />);
    const iframe = container.querySelector('iframe');
    expect(iframe?.getAttribute('loading')).toBe('lazy');
    expect(iframe?.style.height).toBe('600px');
  });

  it('honors an explicit height and eager loading in preview mode', () => {
    const { container } = render(
      <FrozenPageBlock data={{ frozen_page_id: 'abc-123', height: 900 }} previewMode />,
    );
    const iframe = container.querySelector('iframe');
    expect(iframe?.style.height).toBe('900px');
    expect(iframe?.getAttribute('loading')).toBe('eager');
  });

  it('falls back to the default height for a non-positive height', () => {
    const { container } = render(<FrozenPageBlock data={{ frozen_page_id: 'abc-123', height: 0 }} />);
    expect(container.querySelector('iframe')?.style.height).toBe('600px');
  });

  it('renders a heading when provided', () => {
    render(<FrozenPageBlock data={{ frozen_page_id: 'abc-123', heading: 'Imported Section' }} />);
    expect(screen.getByText('Imported Section')).toBeInTheDocument();
  });

  it('shows a placeholder when no frozen page is selected', () => {
    const { container } = render(<FrozenPageBlock data={{}} />);
    expect(container.querySelector('iframe')).toBeNull();
    expect(screen.getByText(/not selected/i)).toBeInTheDocument();
  });
});
