import {fireEvent, render, screen, within} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '@/features/projects/components/MergedResultsTable';
import {createProjectGridItems, type ProjectGridRow} from '@/features/projects/components/projectGrid';
import {
  exportProjectRowsCsv,
  exportProjectRowsExcel,
  exportProjectRowsPdf,
  exportProjectRowsWord,
} from '@/features/projects/components/projectGridExport';

const mockUseAuth = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

vi.mock('@/features/projects/components/projectGridExport', () => ({
  exportProjectRowsCsv: vi.fn(),
  exportProjectRowsExcel: vi.fn(),
  exportProjectRowsPdf: vi.fn(),
  exportProjectRowsWord: vi.fn(),
}));

const baseRow: ProjectGridRow = {
  semester_label: '2025-1 Spring',
  class_code: 'ENGR 120',
  team_number: 'T01',
  team_name: 'Team Alpha',
  project_title: 'Shared Project',
  organization: 'Acme',
  industry: 'Technology',
  abstract: 'A detailed project abstract.',
  student_names: 'Alice, Bob',
  is_presenting: '',
};

const renderTable = (rows: ProjectGridRow[] = [baseRow], props = {}) =>
  render(<MergedResultsTable rows={createProjectGridItems(rows, 'exports')} {...props} />);

const getExportCluster = () => {
  const exportCluster = screen.getByLabelText('Export');
  expect(exportCluster).toBeInTheDocument();
  return exportCluster;
};

describe('MergedResultsTable export buttons', () => {
  beforeEach(() => {
    vi.mocked(exportProjectRowsCsv).mockClear();
    vi.mocked(exportProjectRowsExcel).mockClear();
    vi.mocked(exportProjectRowsPdf).mockClear();
    vi.mocked(exportProjectRowsWord).mockClear();
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue({isAuthenticated: true});
  });

  it('exports visible builder rows to each supported format', () => {
    renderTable();

    const exportCluster = getExportCluster();
    fireEvent.click(within(exportCluster).getByRole('button', {name: 'CSV'}));
    fireEvent.click(within(exportCluster).getByRole('button', {name: 'Excel'}));
    fireEvent.click(within(exportCluster).getByRole('button', {name: 'PDF'}));
    fireEvent.click(within(exportCluster).getByRole('button', {name: 'Microsoft Word'}));

    expect(exportProjectRowsCsv).toHaveBeenCalledWith(
      [baseRow],
      'past-projects',
      expect.objectContaining({
        detailsText: expect.stringContaining('Project 1'),
        note: '',
        title: 'Saved Merged Results',
      }),
    );
    expect(exportProjectRowsExcel).toHaveBeenCalledWith([baseRow], 'past-projects', expect.any(Object));
    expect(exportProjectRowsPdf).toHaveBeenCalledWith([baseRow], 'past-projects', expect.any(Object));
    expect(exportProjectRowsWord).toHaveBeenCalledWith([baseRow], 'past-projects', expect.any(Object));
  });

  it('uses the shared page title and note as export context in shared mode', () => {
    renderTable([baseRow], {
      sharedMode: true,
      title: 'Spring Winners',
      note: 'Curated highlights',
      detailsText: '<strong>Saved details</strong>',
    });

    const exportCluster = getExportCluster();
    fireEvent.click(within(exportCluster).getByRole('button', {name: 'CSV'}));

    expect(exportProjectRowsCsv).toHaveBeenCalledWith(
      [baseRow],
      'past-projects-spring-winners',
      expect.objectContaining({
        detailsText: '<strong>Saved details</strong>',
        note: 'Curated highlights',
        title: 'Spring Winners',
      }),
    );
  });

  it('disables export actions when there are no rows', () => {
    renderTable([]);

    within(getExportCluster())
      .getAllByRole('button')
      .forEach((button) => expect(button).toBeDisabled());
  });
});
