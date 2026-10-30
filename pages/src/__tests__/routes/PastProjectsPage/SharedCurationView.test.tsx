import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {SharedCurationView} from '@/routes/PastProjectsPage/SharedCurationView';

type ViewProps = Parameters<typeof SharedCurationView>[0];

const renderView = (status: Partial<ViewProps['status']>) =>
  render(
    <MemoryRouter>
      <SharedCurationView
        status={{loading: false, error: null, notFound: false, retry: vi.fn(), ...status}}
        conflictMessage={null}
        justSaved={false}
        share={null}
        items={[]}
        onUpdateShare={vi.fn()}
        archive={{rows: [], loading: false, error: null, refetch: vi.fn()}}
        onAddRows={vi.fn()}
      />
    </MemoryRouter>,
  );

describe('SharedCurationView', () => {
  afterEach(() => {
    cleanup();
  });

  it('announces that the curation is loading', () => {
    renderView({loading: true});

    expect(screen.getByRole('status')).toHaveTextContent('Loading curation...');
  });
});
