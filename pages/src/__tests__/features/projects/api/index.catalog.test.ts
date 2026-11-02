import {beforeEach, describe, expect, it, vi} from 'vitest';

// The catalog fields (catalog, is_presenting, current_project_id) that /projects/all/ rows, project details and AI
// search results add, as the grid row mappers, the AI search request and hydration carry them.

const apiMock = vi.hoisted(() => ({get: vi.fn()}));
const authApiMock = vi.hoisted(() => ({post: vi.fn()}));

vi.mock('@/lib/api', () => ({api: apiMock}));
vi.mock('@/features/auth', () => ({
  authApi: authApiMock,
  getAccessToken: vi.fn(),
  isDefinitiveAuthFailure: vi.fn(),
}));

import {
  compactProjectToGridRow,
  hydrateProjectGridRowsSettled,
  searchPastProjectsWithAI,
  toProjectGridRow,
  type CompactPastProjectRow,
  type ProjectDetail,
  type ProjectGridRow,
} from '@/features/projects/api';

const CURRENT_ID = '33333333-3333-4333-8333-333333333333';
const ARCHIVE_ID = '44444444-4444-4444-8444-444444444444';

const compact = (overrides: Partial<CompactPastProjectRow> = {}): CompactPastProjectRow => ({
  id: ARCHIVE_ID,
  semester_label: '2026-2 Fall',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'CAP-101',
  project_title: 'Irrigation Monitor',
  organization: 'Org A',
  industry: 'Agriculture',
  student_names: 'Ada Lovelace',
  track: null,
  presentation_order: null,
  ...overrides,
});

const detail = (overrides: Partial<ProjectDetail> = {}): ProjectDetail => ({
  ...compact(),
  abstract: 'Abstract-101',
  student_names: 'Ada Lovelace',
  ...overrides,
});

const gridRow = (overrides: Partial<ProjectGridRow> = {}): ProjectGridRow => ({
  ...compactProjectToGridRow(compact()),
  ...overrides,
});

describe('grid row mappers and the catalog fields', () => {
  it('carries a current row of /projects/all/ as current, with its presenting flag', () => {
    expect(
      compactProjectToGridRow(compact({id: CURRENT_ID, catalog: 'current', is_presenting: true, current_project_id: null})),
    ).toEqual({
      id: CURRENT_ID,
      semester_label: '2026 Fall',
      class_code: 'CAP',
      team_number: '101',
      // Sheet placeholders are shown as the sheet stores them.
      team_name: 'CAP-101',
      project_title: 'Irrigation Monitor',
      organization: 'Org A',
      industry: 'Agriculture',
      abstract: '',
      student_names: 'Ada Lovelace',
      is_presenting: 'Yes',
      catalog: 'current',
    });
    expect(compactProjectToGridRow(compact({catalog: 'current', is_presenting: false})).is_presenting).toBe('No');
  });

  it('keeps the current project an archive row stands in for, and leaves the fields out when not sent', () => {
    const standIn = compactProjectToGridRow(
      compact({catalog: 'archive', is_presenting: null, current_project_id: CURRENT_ID}),
    );
    expect(standIn).toMatchObject({catalog: 'archive', current_project_id: CURRENT_ID, is_presenting: ''});

    const archiveRow = compactProjectToGridRow(compact({catalog: 'archive', is_presenting: null, current_project_id: null}));
    expect(archiveRow).toMatchObject({catalog: 'archive', is_presenting: ''});
    expect(archiveRow).not.toHaveProperty('current_project_id');

    // A /projects/archive/ row sends none of them.
    const pastRow = compactProjectToGridRow(compact());
    expect(pastRow).not.toHaveProperty('catalog');
    expect(pastRow).not.toHaveProperty('current_project_id');
  });

  it('carries the catalog an AI search result or a project detail sends', () => {
    expect(toProjectGridRow({...detail({id: CURRENT_ID, catalog: 'current', is_presenting: false})})).toMatchObject({
      id: CURRENT_ID,
      catalog: 'current',
      is_presenting: 'No',
    });
    expect(toProjectGridRow(detail())).not.toHaveProperty('catalog');
  });
});

describe('searchPastProjectsWithAI scope', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authApiMock.post.mockResolvedValue({data: {available: true, query: 'solar', results: []}});
  });

  it('asks for every project when the scope is all', async () => {
    await searchPastProjectsWithAI('solar', 10, 'all');

    expect(authApiMock.post).toHaveBeenCalledWith('/projects/past-ai-search/', {query: 'solar', limit: 10, scope: 'all'});
  });

  it('asks for the archive by default', async () => {
    await searchPastProjectsWithAI('solar');

    expect(authApiMock.post).toHaveBeenCalledWith('/projects/past-ai-search/', {query: 'solar', limit: 10, scope: 'past'});
  });
});

describe('hydrateProjectGridRowsSettled and the catalog fields', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const hydrateOne = async (row: ProjectGridRow, answer: ProjectDetail) => {
    apiMock.get.mockResolvedValueOnce({data: answer});
    const {rows} = await hydrateProjectGridRowsSettled([row]);
    return rows[0];
  };

  it('keeps a current row current, by the detail or, from an older server, by its own catalog', async () => {
    const current = gridRow({id: CURRENT_ID, catalog: 'current', is_presenting: 'Yes'});

    await expect(
      hydrateOne(current, detail({id: CURRENT_ID, catalog: 'current', is_presenting: true})),
    ).resolves.toMatchObject({id: CURRENT_ID, catalog: 'current', abstract: 'Abstract-101', is_presenting: 'Yes'});
    expect(apiMock.get).toHaveBeenCalledWith(`/projects/${CURRENT_ID}/`, expect.anything());

    const fromOlderServer = await hydrateOne(current, detail({id: CURRENT_ID, catalog: undefined}));
    expect(fromOlderServer.catalog).toBe('current');
  });

  it("swaps a current row for its archive project once the team is archived, keeping the current id as its alias", async () => {
    const current = gridRow({id: CURRENT_ID, catalog: 'current', is_presenting: 'Yes'});

    const hydrated = await hydrateOne(current, detail({id: ARCHIVE_ID, catalog: 'archive', is_presenting: null}));

    expect(hydrated).toMatchObject({
      id: ARCHIVE_ID,
      catalog: 'archive',
      current_project_id: CURRENT_ID,
      is_presenting: '',
    });
  });

  it('does not keep the catalog of an id the detail no longer has', async () => {
    const current = gridRow({id: CURRENT_ID, catalog: 'current'});

    // An older server sends no catalog: a different id is an archive project's.
    const hydrated = await hydrateOne(current, detail({id: ARCHIVE_ID, catalog: undefined}));

    expect(hydrated.id).toBe(ARCHIVE_ID);
    expect(hydrated).not.toHaveProperty('catalog');
  });

  it('keeps the current project an archive row stands in for while its id is unchanged', async () => {
    const standIn = gridRow({catalog: 'archive', current_project_id: CURRENT_ID});

    await expect(hydrateOne(standIn, detail({catalog: 'archive', is_presenting: null}))).resolves.toMatchObject({
      id: ARCHIVE_ID,
      catalog: 'archive',
      current_project_id: CURRENT_ID,
    });
  });

  it('adds no catalog fields to a past project row', async () => {
    const hydrated = await hydrateOne(gridRow(), detail());

    expect(hydrated).toEqual({...gridRow(), abstract: 'Abstract-101'});
  });
});
