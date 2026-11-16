import {render} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {PastProjectsPage} from '@/routes/projects/PastProjectsPage/PastProjectsPage';
import {type PastProjectShare} from '@/features/projects/api';
import {sampleRow} from '@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageState';

export const shareFixture = (
    overrides: Partial<PastProjectShare> = {},
): PastProjectShare => ({
    id: 'share-abc',
    name: 'Spring finalists',
    rows: [sampleRow],
    note: 'Original note',
    details_text: '<strong>Details</strong>',
    version: 4,
    share_url: '/past-projects/share-abc',
    can_edit: true,
    created_at: '2026-06-08T00:00:00Z',
    ...overrides,
});

export const renderPage = () =>
    render(
        <MemoryRouter initialEntries={['/past-projects']}>
            <PastProjectsPage/>
        </MemoryRouter>,
    );
