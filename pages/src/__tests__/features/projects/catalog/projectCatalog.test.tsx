import {renderHook} from '@testing-library/react';
import type {ReactNode} from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {compactProjectToGridRow, type CompactPastProjectRow} from '@/features/projects/api';
import {ALL_PROJECTS_CATALOG, PAST_PROJECTS_CATALOG} from '@/features/projects/catalog/catalogs';
import {ProjectCatalogContext, useProjectCatalog} from '@/features/projects/catalog/projectCatalog';

const {mockFetchAllPastProjectArchive, mockSearchPastProjectArchiveIds} = vi.hoisted(() => ({
  mockFetchAllPastProjectArchive: vi.fn(),
  mockSearchPastProjectArchiveIds: vi.fn(),
}));

vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  fetchAllPastProjectArchive: (...args: unknown[]) => mockFetchAllPastProjectArchive(...args),
  searchPastProjectArchiveIds: (...args: unknown[]) => mockSearchPastProjectArchiveIds(...args),
}));

const archiveRow: CompactPastProjectRow = {
  id: '11111111-1111-4111-8111-111111111111',
  semester_label: '2025-1 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'Solar Team',
  project_title: 'Solar Project',
  organization: 'Solar Org',
  industry: 'Energy',
  student_names: 'Ada Lovelace',
  track: null,
  presentation_order: null,
};

afterEach(() => {
  mockFetchAllPastProjectArchive.mockReset();
  mockSearchPastProjectArchiveIds.mockReset();
});

describe('useProjectCatalog', () => {
  it('is Past Projects without a provider, so every page and test that sets none is unchanged', () => {
    const {result} = renderHook(() => useProjectCatalog());

    expect(result.current).toBe(PAST_PROJECTS_CATALOG);
  });

  it('is the catalog a provider gives', () => {
    const wrapper = ({children}: {children: ReactNode}) => (
      <ProjectCatalogContext.Provider value={ALL_PROJECTS_CATALOG}>{children}</ProjectCatalogContext.Provider>
    );

    const {result} = renderHook(() => useProjectCatalog(), {wrapper});

    expect(result.current).toBe(ALL_PROJECTS_CATALOG);
  });
});

describe('PAST_PROJECTS_CATALOG', () => {
  it('loads the whole published archive as grid rows', async () => {
    mockFetchAllPastProjectArchive.mockResolvedValue([archiveRow]);
    const signal = new AbortController().signal;

    await expect(PAST_PROJECTS_CATALOG.loadRows(signal)).resolves.toEqual([compactProjectToGridRow(archiveRow)]);
    expect(mockFetchAllPastProjectArchive).toHaveBeenCalledWith({}, signal);
  });

  it("asks the archive's server search which projects match", async () => {
    const ids = new Set([archiveRow.id]);
    mockSearchPastProjectArchiveIds.mockResolvedValue(ids);
    const signal = new AbortController().signal;

    await expect(PAST_PROJECTS_CATALOG.searchRemote('solar', signal)).resolves.toBe(ids);
    expect(mockSearchPastProjectArchiveIds).toHaveBeenCalledWith('solar', signal);
  });

  it('names the list as the Past Projects page does', () => {
    const {copy} = PAST_PROJECTS_CATALOG;

    expect(PAST_PROJECTS_CATALOG).toMatchObject({key: 'past', path: '/past-projects', title: 'Past Projects', aiScope: 'past'});
    expect(copy.refreshed(1)).toBe('Search table refreshed from the latest past-project archive.');
    expect(copy.refreshed(2)).toBe('Search tables refreshed from the latest past-project archive.');
    expect(copy.handoverMissing(1)).toBe('1 project from the Past Projects widget is no longer in the archive.');
    expect(copy.handoverMissing(3)).toBe('3 projects from the Past Projects widget are no longer in the archive.');
  });
});

describe('ALL_PROJECTS_CATALOG', () => {
  it('names the All Projects page and asks AI search for every project', () => {
    const {copy} = ALL_PROJECTS_CATALOG;

    expect(ALL_PROJECTS_CATALOG).toMatchObject({key: 'all', path: '/all-projects', title: 'All Projects', aiScope: 'all'});
    expect(copy.loading).toBe('Loading projects...');
    expect(copy.aiPlaceholder).toBe('Ask AI to find relevant projects...');
    expect(copy.handoverMissing(2)).toBe('2 projects from the All Projects widget are no longer listed.');
  });
});
