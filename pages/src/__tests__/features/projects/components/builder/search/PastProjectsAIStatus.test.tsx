import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {PastProjectsAIStatus} from '@/features/projects/components/builder/search/PastProjectsAIStatus';

// The AI search's and the per-table saves' status line: words and the tone's colour, no icons.
describe('PastProjectsAIStatus', () => {
  afterEach(cleanup);

  it('reports a success in words alone, in the success tone', () => {
    const {container} = render(<PastProjectsAIStatus tone="success" message="3 projects added to the curation draft." />);

    const status = screen.getByRole('status');
    expect(status).toHaveClass('past-projects-ai-search-message', 'is-success');
    expect(status).toHaveTextContent('3 projects added to the curation draft.');
    expect(container.querySelector('svg')).toBeNull();
  });

  it('reports an error as an alert, without an icon', () => {
    const {container} = render(<PastProjectsAIStatus tone="error" message="AI search is unavailable." />);

    expect(screen.getByRole('alert')).toHaveClass('is-error');
    expect(screen.getByRole('alert')).toHaveTextContent('AI search is unavailable.');
    expect(container.querySelector('svg')).toBeNull();
  });

  it('shows the site loading indicator while something loads', () => {
    render(<PastProjectsAIStatus tone="loading" message="Adding 3 projects…" announce={false} />);

    const label = screen.getByText('Adding 3 projects…');
    expect(label).toHaveClass('loading-indicator-label');
    expect(label.closest('.past-projects-ai-search-message')).toHaveClass('is-loading');
    expect(label.parentElement?.querySelector('.loading-indicator-spinner')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.queryByRole('status')).toBeNull();
  });
});
