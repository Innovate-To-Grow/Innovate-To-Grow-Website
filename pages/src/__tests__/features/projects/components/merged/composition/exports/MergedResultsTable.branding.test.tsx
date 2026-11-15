import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {createProjectGridItems, type ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {MergedResultsTable} from '@/features/projects/components/merged/composition/MergedResultsTable';

// A curation holding a current-semester project (built on All Projects) is named after All Projects on its shared
// page and in its exports; one of archive projects only keeps the Past Projects names.

const mockUseAuth = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {...actual, useAuth: () => mockUseAuth()};
});

// The exporters load exceljs / jspdf and download; their own tests cover them. Here only what they are given.
const exportMocks = vi.hoisted(() => ({exportProjectRowsPdf: vi.fn()}));
vi.mock('@/features/projects/components/export/formats/pdfExport', () => ({
  exportProjectRowsPdf: exportMocks.exportProjectRowsPdf,
}));

const makeRow = (overrides: Partial<ProjectGridRow>): ProjectGridRow => ({
  semester_label: '2025 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'CAP-101',
  project_title: 'Archive Project',
  organization: 'Acme',
  industry: 'Energy',
  abstract: 'Abstract-101',
  student_names: 'Ada',
  is_presenting: '',
  ...overrides,
});

const ARCHIVE_ROW = makeRow({id: '11111111-1111-4111-8111-111111111111', catalog: 'archive'});
const CURRENT_ROW = makeRow({
  id: '22222222-2222-4222-8222-222222222222',
  semester_label: '2026 Fall',
  team_number: '102',
  project_title: 'Current Project',
  organization: 'Blue Diamond',
  catalog: 'current',
  is_presenting: 'Yes',
});

const items = (rows: ProjectGridRow[]) => createProjectGridItems(rows, 'test');

/** Exports the list as PDF and returns the file name and context the exporter was given. */
const exportPdf = async (container: HTMLElement) => {
  const exportCluster = container.querySelector('.project-grid-toolbar-cluster[aria-label="Export"]') as HTMLElement;
  fireEvent.click(within(exportCluster).getByRole('button', {name: 'PDF'}));
  await waitFor(() => expect(exportMocks.exportProjectRowsPdf).toHaveBeenCalledTimes(1));
  const [, fileBaseName, context] = exportMocks.exportProjectRowsPdf.mock.calls[0];
  return {fileBaseName, context};
};

describe('MergedResultsTable branding', () => {
  beforeEach(() => {
    mockUseAuth.mockReset().mockReturnValue({isAuthenticated: true});
    exportMocks.exportProjectRowsPdf.mockReset().mockResolvedValue(undefined);
  });

  afterEach(cleanup);

  it('heads a shared curation with a current-semester project as All Projects, and exports it so', async () => {
    const {container} = render(
      <MergedResultsTable rows={items([ARCHIVE_ROW, CURRENT_ROW])} sharedMode title="Fall picks" />,
    );

    expect(screen.getByText('Curation · All Projects')).toHaveClass('itg-eyebrow');
    expect(screen.queryByText('Curation · Past Projects')).toBeNull();
    expect(await exportPdf(container)).toEqual({
      fileBaseName: 'projects-fall-picks',
      context: {title: 'Fall picks', note: '', heading: 'Innovate to Grow Projects'},
    });
  });

  it('exports a draft with a current-semester project as All Projects', async () => {
    const {container} = render(<MergedResultsTable rows={items([ARCHIVE_ROW, CURRENT_ROW])} onCreateShare={vi.fn()} />);

    const {fileBaseName, context} = await exportPdf(container);
    expect(fileBaseName).toBe('projects');
    expect(context).toMatchObject({title: 'Curation Draft', heading: 'Innovate to Grow Projects'});
  });

  it('suggests the name the server gives a draft with a current-semester project saved without one', () => {
    const {rerender} = render(<MergedResultsTable rows={items([ARCHIVE_ROW, CURRENT_ROW])} onCreateShare={vi.fn()} />);
    expect(screen.getByLabelText(/curation name/i)).toHaveAttribute('placeholder', 'Project Curation');

    rerender(<MergedResultsTable rows={items([ARCHIVE_ROW])} onCreateShare={vi.fn()} />);
    expect(screen.getByLabelText(/curation name/i)).toHaveAttribute('placeholder', 'Past Project Curation');
  });

  it('exports the archive projects a search narrowed the draft to under the Past Projects names', async () => {
    const {container} = render(<MergedResultsTable rows={items([ARCHIVE_ROW, CURRENT_ROW])} onCreateShare={vi.fn()} />);

    fireEvent.change(screen.getByRole('searchbox'), {target: {value: 'Archive Project'}});
    const {fileBaseName, context} = await exportPdf(container);

    expect(fileBaseName).toBe('past-projects');
    expect(context.heading).toBeUndefined();
  });
});
