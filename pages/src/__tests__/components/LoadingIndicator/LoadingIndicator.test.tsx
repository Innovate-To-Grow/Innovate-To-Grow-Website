import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {LoadingIndicator} from '@/components/LoadingIndicator';

describe('LoadingIndicator', () => {
  afterEach(cleanup);

  it('shows the label beside a spinner that assistive technology skips', () => {
    const {container} = render(<LoadingIndicator label="Loading project data…" />);

    const indicator = container.firstElementChild as HTMLElement;
    expect(indicator).toHaveClass('loading-indicator');
    expect(indicator).toHaveTextContent(/^Loading project data…$/);
    expect(screen.getByText('Loading project data…')).toHaveClass('loading-indicator-label');
    const spinner = indicator.querySelector('.loading-indicator-spinner');
    expect(spinner).toHaveAttribute('aria-hidden', 'true');
    expect(spinner).toBeEmptyDOMElement();
  });

  it('carries no role, so the host keeps its own status region', () => {
    render(
      <p role="status">
        <LoadingIndicator label="Loading…" />
      </p>,
    );

    expect(screen.getAllByRole('status')).toHaveLength(1);
    expect(screen.getByRole('status')).toHaveTextContent('Loading…');
    expect(document.querySelector('.loading-indicator')).not.toHaveAttribute('role');
  });

  it("adds the host's class next to its own", () => {
    const {container} = render(<LoadingIndicator label="Loading curation…" className="shared-loading" />);

    expect(container.firstElementChild).toHaveClass('loading-indicator', 'shared-loading');
    expect(container.firstElementChild?.className).toBe('loading-indicator shared-loading');
  });

  it('keeps the label the only child of its element, for page translation', () => {
    render(<LoadingIndicator label="Loading project…" />);

    const label = screen.getByText('Loading project…');
    expect(label.childNodes).toHaveLength(1);
    expect(label.firstChild?.nodeType).toBe(Node.TEXT_NODE);
  });
});
