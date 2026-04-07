import {render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {EventArchivePage} from './EventArchivePage';

const mockUsePastProjectsData = vi.fn();

vi.mock('../../hooks/usePastProjectsData', () => ({
  usePastProjectsData: () => mockUsePastProjectsData(),
}));

vi.mock('../../components/ScheduleGrid', () => ({
  ScheduleGrid: ({rows}: {rows: Array<Record<string, string>>}) => (
    <div data-testid="schedule-rows">{rows.map((row) => row['Year-Semester']).join('|')}</div>
  ),
}));

vi.mock('../../components/SheetsDataTable', () => ({
  SheetsDataTable: ({rows}: {rows: Array<Record<string, string>>}) => (
    <div data-testid="table-rows">{rows.map((row) => row['Year-Semester']).join('|')}</div>
  ),
}));

describe('EventArchivePage', () => {
  beforeEach(() => {
    mockUsePastProjectsData.mockReset();
    mockUsePastProjectsData.mockReturnValue({
      rows: [
        {
          'Year-Semester': '2025-2 Fall',
          Class: 'CAP',
          Order: '1',
          Track: '1',
          'Team#': '101',
          Organization: 'Matching Org',
        },
        {
          'Year-Semester': '2025-1 Spring',
          Class: 'CAP',
          Order: '1',
          Track: '1',
          'Team#': '202',
          Organization: 'Wrong Semester',
        },
      ],
      loading: false,
      error: null,
    });
  });

  it('filters archive rows to the selected event semester', () => {
    render(
      <MemoryRouter initialEntries={['/events/2025-fall']}>
        <Routes>
          <Route path="/events/:eventSlug" element={<EventArchivePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByTestId('schedule-rows')).toHaveTextContent('2025-2 Fall');
    expect(screen.getByTestId('table-rows')).toHaveTextContent('2025-2 Fall');
    expect(screen.getByTestId('schedule-rows')).not.toHaveTextContent('2025-1 Spring');
    expect(screen.getByTestId('table-rows')).not.toHaveTextContent('2025-1 Spring');
  });
});
