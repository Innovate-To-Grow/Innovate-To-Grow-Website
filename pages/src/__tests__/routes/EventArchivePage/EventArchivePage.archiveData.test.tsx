import {render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import type {CompactPastProjectRow} from '@/features/projects/api';
import {EventArchivePage} from '@/routes/EventArchivePage/EventArchivePage';

const mocks = vi.hoisted(() => ({get: vi.fn()}));

// The real usePastProjectsData runs against a mocked HTTP client, so the rows reach the page in the shape the hook
// gives them, not the shape a test assumes.
vi.mock('@/lib/api', () => ({
    api: {get: mocks.get},
}));

vi.mock('@/features/events/components/ScheduleGrid', () => ({
    ScheduleGrid: ({rows}: { rows: Array<Record<string, string>> }) => (
        <div data-testid="schedule-rows">{rows.map((row) => row['Team#']).join('|')}</div>
    ),
}));

vi.mock('@/components/SheetsDataTable', () => ({
    SheetsDataTable: ({rows, loading}: { rows: Array<Record<string, string>>; loading: boolean }) => (
        <div data-testid="table-rows" data-loading={String(loading)}>{rows.map((row) => row['Team#']).join('|')}</div>
    ),
}));

const archiveRow = (overrides: Partial<CompactPastProjectRow>): CompactPastProjectRow => ({
    id: 'p-1',
    semester_label: '2025-2 Fall',
    class_code: 'CAP',
    team_number: '101',
    team_name: 'Team A',
    project_title: 'Project A',
    organization: 'Org A',
    industry: 'Energy',
    track: 1,
    presentation_order: 1,
    ...overrides,
});

describe('EventArchivePage with archive data', () => {
    beforeEach(() => {
        mocks.get.mockReset();
    });

    it('lists the semester the archive API returns for the event', async () => {
        const results = [archiveRow({}), archiveRow({id: 'p-2', team_number: '102', presentation_order: 2})];
        mocks.get.mockResolvedValue({data: {count: results.length, next: null, previous: null, results}});

        render(
            <MemoryRouter initialEntries={['/events/2025-fall']}>
                <Routes>
                    <Route path="/events/:eventSlug" element={<EventArchivePage/>}/>
                </Routes>
            </MemoryRouter>,
        );

        await waitFor(() => expect(screen.getByTestId('table-rows')).toHaveAttribute('data-loading', 'false'));
        expect(screen.getByTestId('table-rows')).toHaveTextContent('101|102');
        expect(screen.getByTestId('schedule-rows')).toHaveTextContent('101|102');
        expect(mocks.get).toHaveBeenCalledWith(
            '/projects/archive/',
            expect.objectContaining({params: expect.objectContaining({year: 2025, season: 2})}),
        );
    });
});
