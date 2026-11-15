import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/builder/composition/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {
  aiResult,
  type BuilderProps,
  ID_CURRENT,
  ID_GONE,
  inAllProjects,
  makeRow,
  RAW_ERROR,
  ROWS,
  searchTable,
  signedIn,
  signedOut,
} from '@/__tests__/features/projects/components/builder/composition/catalog/pastProjectsBuilderAllProjectsFixtures';

// On All Projects the builder searches every project, this semester's teams and the archive: its messages, help,
// AI search and the widget's hand-over to the full page name that list and that page, not the archive.

const mockUseAuth = vi.fn();
const mockSearchPastProjectsWithAI = vi.fn();
const mockHydrateProjectGridRowsSettled = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {...actual, useAuth: () => mockUseAuth()};
});

vi.mock('@/features/projects/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/projects/api')>();
  return {
    ...actual,
    searchPastProjectsWithAI: (...args: unknown[]) => mockSearchPastProjectsWithAI(...args),
    hydrateProjectGridRowsSettled: (...args: unknown[]) => mockHydrateProjectGridRowsSettled(...args),
  };
});

const builder = (props: BuilderProps = {}) =>
  inAllProjects(
    <PastProjectsBuilder
      rows={props.rows ?? ROWS}
      loading={props.loading ?? false}
      error={props.error ?? null}
      onRefreshRows={props.onRefreshRows}
      onCreateShare={vi.fn()}
    />,
  );

describe('PastProjectsBuilder on All Projects', () => {
  beforeEach(() => {
    mockUseAuth.mockReset().mockReturnValue(signedOut);
    mockSearchPastProjectsWithAI.mockReset();
    mockHydrateProjectGridRowsSettled.mockReset().mockImplementation(async (rows: ProjectGridRow[]) => ({
      rows: rows.map((row) => ({...row, abstract: `${row.project_title} abstract`})),
      failedIndexes: [],
      unavailableIndexes: [],
    }));
    localStorage.clear();
    sessionStorage.clear();
  });

  afterEach(() => {
    cleanup();
    window.history.replaceState(null, '', '/');
    vi.restoreAllMocks();
  });

  describe('loading the list', () => {
    it('says it is loading projects, not past projects', () => {
      render(builder({rows: [], loading: true}));

      expect(screen.getByText('Loading projects…').closest('[role="status"]')).not.toBeNull();
      expect(screen.queryByText(/past projects/i)).toBeNull();
    });

    it('says the project list could not be loaded when its first load failed', () => {
      render(builder({rows: [], error: RAW_ERROR, onRefreshRows: vi.fn()}));

      expect(screen.getByRole('alert')).toHaveTextContent(
        'The project list could not be loaded. Check your connection and try again.',
      );
      expect(screen.queryByText(/past-project archive/)).toBeNull();
    });

    it('names the project list in the help', () => {
      const {container} = render(builder());
      const help = container.querySelector('.past-projects-help-details') as HTMLElement;

      expect(help).toHaveTextContent('Adds another search table over the same project list, so you can try');
      expect(help).toHaveTextContent('load matching projects, then use the same checkboxes');
      expect(help).toHaveTextContent('Refresh Search Table reloads the project list and starts that table over');
      expect(help).not.toHaveTextContent(/archive|past project/i);
    });
  });

  describe('refreshing a search table', () => {
    it('reloads it from the latest project list', () => {
      const onRefreshRows = vi.fn();
      const {rerender} = render(builder({onRefreshRows}));

      fireEvent.click(within(searchTable('Search Table')).getByRole('button', {name: 'Refresh Search Table'}));
      expect(onRefreshRows).toHaveBeenCalledTimes(1);
      expect(screen.getByText('Refreshing this search table from the latest project list…')).toBeInTheDocument();

      const delta = makeRow({id: ID_GONE, team_number: '103', project_title: 'Delta Project'});
      rerender(builder({rows: [...ROWS, delta], onRefreshRows}));
      expect(screen.getByText('Search table refreshed from the latest project list.')).toBeInTheDocument();
    });

    it('says the project list could not be loaded when a refresh fails', () => {
      const onRefreshRows = vi.fn();
      const {rerender} = render(builder({onRefreshRows}));

      fireEvent.click(within(searchTable('Search Table')).getByRole('button', {name: 'Refresh Search Table'}));
      rerender(builder({error: RAW_ERROR, onRefreshRows}));

      expect(within(searchTable('Search Table')).getByRole('alert')).toHaveTextContent(
        'This table was not refreshed: the project list could not be loaded. Its rows are unchanged; ' +
          'click Refresh Search Table to try again.',
      );
    });
  });

  describe('the AI search table', () => {
    beforeEach(() => mockUseAuth.mockReturnValue(signedIn));

    it('asks AI search to rank every project and loads a current project that links to its own page', async () => {
      let answer!: (value: unknown) => void;
      mockSearchPastProjectsWithAI.mockReturnValue(new Promise((resolve) => (answer = resolve)));
      render(builder());

      fireEvent.click(screen.getByRole('button', {name: '+ AI Search Table'}));
      const aiTable = searchTable('AI Search Table');
      expect(aiTable).toHaveTextContent(
        'Use AI to load matching projects into this table, then check the projects you want and click Add to Curation.',
      );
      fireEvent.change(within(aiTable).getByPlaceholderText('Ask about projects…'), {
        target: {value: 'irrigation'},
      });
      fireEvent.click(within(aiTable).getByRole('button', {name: 'Search'}));

      expect(mockSearchPastProjectsWithAI).toHaveBeenCalledWith('irrigation', 10, 'all');
      expect(within(aiTable).getByText('Searching projects with AI…').closest('[role="status"]')).not.toBeNull();

      await act(async () =>
        answer({
          available: true,
          query: 'irrigation',
          results: [aiResult({catalog: 'current', is_presenting: true})],
          usage: {inputTokens: 10, outputTokens: 2, totalTokens: 12},
        }),
      );
      const results = searchTable('AI Search Table: irrigation');
      const link = within(results.querySelector('.project-grid-table-wrap') as HTMLElement).getByRole('link', {
        name: /Irrigation Sensor/,
      });
      // Opened in a new tab, like every builder row's link, so the curation stays.
      expect(link).toHaveAttribute('href', `${window.location.origin}/projects/${ID_CURRENT}`);
    });

    it('says it found no matching projects', async () => {
      mockSearchPastProjectsWithAI.mockResolvedValue({available: true, query: 'hydroponics', results: [], usage: null});
      render(builder());

      fireEvent.click(screen.getByRole('button', {name: '+ AI Search Table'}));
      const aiTable = searchTable('AI Search Table');
      fireEvent.change(within(aiTable).getByRole('searchbox'), {target: {value: 'hydroponics'}});
      fireEvent.click(within(aiTable).getByRole('button', {name: 'Search'}));

      expect(await within(aiTable).findByText('AI search did not find matching projects.')).toBeInTheDocument();
    });
  });
});
