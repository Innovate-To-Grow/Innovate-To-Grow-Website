import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ALL_PROJECTS_CATALOG} from '@/features/projects/catalog/catalogs';
import {ProjectCatalogContext} from '@/features/projects/catalog/projectCatalog';
import {SearchTableCard} from '@/features/projects/components/search/cards/SearchTableCard';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

// On All Projects a search table's rows are every project, and its server search is the whole list's
// (/projects/all/), which reads a current-semester project's abstract too.

const {searchArchive, searchAll} = vi.hoisted(() => ({searchArchive: vi.fn(), searchAll: vi.fn()}));
vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  searchPastProjectArchiveIds: searchArchive,
  searchAllProjectIds: searchAll,
}));

const CURRENT_ID = '33333333-3333-4333-8333-333333333333';
const ARCHIVE_ID = '11111111-1111-4111-8111-111111111111';

const row = (overrides: Partial<ProjectGridRow>): ProjectGridRow => ({
  semester_label: '2024-1 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'CAP-101',
  project_title: 'Archive Project',
  organization: 'Acme',
  industry: 'Energy',
  abstract: '',
  student_names: 'Ada',
  is_presenting: '',
  ...overrides,
});

const ROWS = [
  row({id: CURRENT_ID, semester_label: '2026 Fall', project_title: 'Current Project', catalog: 'current'}),
  row({id: ARCHIVE_ID, team_number: '102', catalog: 'archive'}),
];

describe('SearchTableCard on All Projects', () => {
  afterEach(() => {
    cleanup();
    searchArchive.mockReset();
    searchAll.mockReset();
  });

  it("asks the whole list's server search, and finds a current project by its abstract", async () => {
    searchAll.mockResolvedValue(new Set([CURRENT_ID]));
    render(
      <ProjectCatalogContext.Provider value={ALL_PROJECTS_CATALOG}>
        <SearchTableCard
          canRemove={false}
          initialRows={ROWS}
          tableId="table-1"
          title="Search Table"
          onRemove={vi.fn()}
          onMergeSelected={vi.fn()}
        />
      </ProjectCatalogContext.Provider>,
    );

    fireEvent.change(screen.getByRole('searchbox'), {target: {value: 'Abstract-101'}});

    const table = await screen.findByRole('table', {name: 'Search Table'});
    expect(await within(table).findByRole('link', {name: /Current Project/})).toHaveAttribute(
      'href',
      `${window.location.origin}/projects/${CURRENT_ID}`,
    );
    expect(within(table).queryByRole('link', {name: /Archive Project/})).toBeNull();
    expect(searchAll).toHaveBeenCalledWith('Abstract-101', expect.any(AbortSignal));
    expect(searchArchive).not.toHaveBeenCalled();
  });
});
