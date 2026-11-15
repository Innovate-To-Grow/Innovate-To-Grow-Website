import {render} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {vi} from 'vitest';

import type {PastProjectShare} from '@/features/projects/api';
import {SharedCurationView} from '@/routes/projects/PastProjectsPage/SharedCurationView';

type ViewProps = Parameters<typeof SharedCurationView>[0];

export const SHARE: PastProjectShare = {
  id: 'share-1',
  name: 'Water projects',
  rows: [],
  note: '',
  details_text: '',
  version: 1,
  share_url: '/past-projects/share-1',
  can_edit: false,
  created_at: '2026-05-01T00:00:00Z',
};

export const view = (status: Partial<ViewProps['status']>, share: PastProjectShare | null = null) => (
  <MemoryRouter>
    <SharedCurationView
      status={{loading: false, error: null, notFound: false, retry: vi.fn(), ...status}}
      conflictMessage={null}
      justSaved={false}
      share={share}
      items={[]}
      onUpdateShare={vi.fn()}
      projects={{rows: [], loading: false, error: null, refetch: vi.fn()}}
      onAddRows={vi.fn()}
    />
  </MemoryRouter>
);

export const renderView = (status: Partial<ViewProps['status']>) => render(view(status));
