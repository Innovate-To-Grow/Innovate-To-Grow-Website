import {act, renderHook} from '@testing-library/react';
import type {ReactNode} from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ALL_PROJECTS_CATALOG} from '@/features/projects/catalog/catalogs';
import {ProjectCatalogContext} from '@/features/projects/catalog/projectCatalog';
import {useSearchTables} from '@/features/projects/components/search/state/useSearchTables';

// An AI search table ranks the list the page searches: the archive on Past Projects (the default scope), every
// project on All Projects, whose words its messages use.

const {mockSearchPastProjectsWithAI} = vi.hoisted(() => ({mockSearchPastProjectsWithAI: vi.fn()}));
vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  searchPastProjectsWithAI: (...args: unknown[]) => mockSearchPastProjectsWithAI(...args),
}));

const allProjects = ({children}: {children: ReactNode}) => (
  <ProjectCatalogContext.Provider value={ALL_PROJECTS_CATALOG}>{children}</ProjectCatalogContext.Provider>
);

const renderTables = (wrapper?: typeof allProjects) =>
  renderHook(() => useSearchTables({idPrefix: 'table', isAuthenticated: true, rows: [], onMessage: vi.fn()}), {
    wrapper,
  });

/** Adds the AI table and runs `query` in it; returns the AI table's state while the search runs. */
const startAISearch = (tables: ReturnType<typeof renderTables>, query: string) => {
  act(() => {
    tables.result.current.addAISearchTable();
  });
  const aiTable = tables.result.current.searchTables.find((table) => table.type === 'ai')!;
  act(() => {
    void tables.result.current.runAISearch(aiTable.id, query);
  });
  return () => tables.result.current.searchTables.find((table) => table.id === aiTable.id)!;
};

describe('useSearchTables AI search', () => {
  afterEach(() => mockSearchPastProjectsWithAI.mockReset());

  it('asks Past Projects\' AI search to rank the archive only', () => {
    mockSearchPastProjectsWithAI.mockReturnValue(new Promise(() => {}));
    const aiTable = startAISearch(renderTables(), 'solar');

    expect(mockSearchPastProjectsWithAI).toHaveBeenCalledWith('solar', 10, 'past');
    expect(aiTable()).toMatchObject({message: 'Searching past projects with AI…', messageTone: 'loading'});
  });

  it('asks All Projects to rank every project, and names them so', async () => {
    let answer!: (value: unknown) => void;
    mockSearchPastProjectsWithAI.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    const aiTable = startAISearch(renderTables(allProjects), 'irrigation');

    expect(mockSearchPastProjectsWithAI).toHaveBeenCalledWith('irrigation', 10, 'all');
    expect(aiTable()).toMatchObject({message: 'Searching projects with AI…', messageTone: 'loading'});

    await act(async () => answer({available: true, query: 'irrigation', results: [], usage: null}));
    expect(aiTable()).toMatchObject({message: 'AI search did not find matching projects.', messageTone: 'error'});
  });

  it('names an AI table after its question, clipping a long one with an ellipsis', async () => {
    const question = 'Projects that measure soil moisture with low-cost sensors for small farms in the valley';
    const row = {
      id: 'ai-1', semester_label: '2024-1 Spring', class_code: 'CAP', team_number: '101', team_name: 'Team',
      project_title: 'Soil Sensors', organization: 'Org', industry: 'Agriculture', abstract: '', student_names: '',
      track: null, presentation_order: null,
    };
    mockSearchPastProjectsWithAI.mockResolvedValue({available: true, query: question, results: [row], usage: null});
    const tables = renderTables();
    const aiTable = startAISearch(tables, question);
    await act(async () => {});

    expect(aiTable().title).toBe(`AI Search Table: ${question.slice(0, 51).trim()}…`);
  });
});
