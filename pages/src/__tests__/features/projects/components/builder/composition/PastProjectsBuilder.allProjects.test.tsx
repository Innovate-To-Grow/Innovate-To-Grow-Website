import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import type {ReactElement} from 'react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type {ProjectTableRow} from '@/features/projects/api';
import {ALL_PROJECTS_CATALOG} from '@/features/projects/catalog/catalogs';
import {ProjectCatalogContext} from '@/features/projects/catalog/projectCatalog';
import {PastProjectsBuilder} from '@/features/projects/components/builder/composition/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

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

const ID_CURRENT = '11111111-1111-4111-8111-111111111111';
const ID_ARCHIVE = '22222222-2222-4222-8222-222222222222';
const ID_GONE = '33333333-3333-4333-8333-333333333333';

const makeRow = (overrides: Partial<ProjectGridRow>): ProjectGridRow => ({
  semester_label: '2025-1 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'CAP-101',
  project_title: 'Alpha Project',
  organization: 'Acme',
  industry: 'Technology',
  abstract: '',
  student_names: '',
  is_presenting: '',
  ...overrides,
});

// A current-semester row, as /projects/all/ lists it first, then an archive row.
const ROWS: ProjectGridRow[] = [
  makeRow({id: ID_CURRENT, semester_label: '2026 Fall', catalog: 'current', is_presenting: 'Yes'}),
  makeRow({id: ID_ARCHIVE, team_number: '102', project_title: 'Bravo Project', catalog: 'archive'}),
];

const RAW_ERROR = 'Request failed with status code 503';
const signedOut = {isAuthenticated: false, isInitializing: false, unverified: false, user: null};
const signedIn = {
  isAuthenticated: true,
  isInitializing: false,
  unverified: false,
  user: {member_uuid: 'member-1', email: 'member@example.com'},
};

const inAllProjects = (ui: ReactElement) => (
  <ProjectCatalogContext.Provider value={ALL_PROJECTS_CATALOG}>{ui}</ProjectCatalogContext.Provider>
);

interface BuilderProps {
  rows?: ProjectGridRow[];
  loading?: boolean;
  error?: string | null;
  onRefreshRows?: () => void;
}

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

const searchTable = (name: string) => screen.getByRole('heading', {level: 3, name}).closest('section') as HTMLElement;
const draftSection = () =>
  screen.getByRole('heading', {level: 2, name: /curation draft/i}).closest('section') as HTMLElement;

/** Checks the rows and adds them; their details load first, so the draft card shows a moment later. */
const addToCuration = async (...titles: string[]) => {
  for (const title of titles) {
    fireEvent.click(screen.getAllByLabelText(`Select ${title}`)[0]);
  }
  fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
  await screen.findByRole('heading', {level: 2, name: /curation draft/i});
};

const aiResult = (overrides: Partial<ProjectTableRow>): ProjectTableRow => ({
  id: ID_CURRENT,
  semester_label: '2026 Fall',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'CAP-101',
  project_title: 'Irrigation Sensor',
  organization: 'Acme',
  industry: 'Agriculture',
  abstract: 'Abstract-101',
  student_names: 'Ada Lovelace',
  track: 1,
  presentation_order: 1,
  ...overrides,
});

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

  describe('in the widget', () => {
    const NEW_TAB_LINK_NAME = /^Continue in All Projects\s*\(opens in a new tab\)$/;

    beforeEach(() => window.history.replaceState(null, '', '/_embed/test-all'));

    it('continues on the full All Projects page in a new tab, with the draft', async () => {
      render(builder());
      await addToCuration('Alpha Project', 'Bravo Project');

      const continueLinks = within(draftSection()).getAllByRole('link', {name: NEW_TAB_LINK_NAME});
      expect(continueLinks).toHaveLength(2);
      for (const link of continueLinks) {
        expect(link).toHaveAttribute('href', `/all-projects#curation-draft=${ID_CURRENT},${ID_ARCHIVE}`);
        expect(link).toHaveAttribute('target', '_blank');
        expect(link.firstChild).toHaveProperty('textContent', 'Continue in All Projects');
      }
      expect(draftSection().querySelector('a[href^="/past-projects"]')).toBeNull();
    });

    it("offers AI search's sign-in on the full All Projects page, with the draft", async () => {
      render(builder());
      await addToCuration('Alpha Project');

      fireEvent.click(screen.getByRole('button', {name: 'AI Search Table'}));

      const dialog = screen.getByRole('dialog', {name: 'Sign in required'});
      expect(within(dialog).getByRole('link', {name: NEW_TAB_LINK_NAME})).toHaveAttribute(
        'href',
        `/all-projects#curation-draft=${ID_CURRENT}`,
      );
      expect(dialog).toHaveTextContent(
        'AI search needs you to sign in on the Innovate to Grow site. All Projects opens in a new tab, with your ' +
          'curation draft, where you can sign in and use it.',
      );
    });
  });

  describe('on the full page', () => {
    it('adds the projects the All Projects widget handed over, and names the ones no longer listed', async () => {
      window.history.replaceState(null, '', `/all-projects#curation-draft=${ID_CURRENT},${ID_GONE}`);
      render(builder());
      await screen.findByRole('heading', {level: 2, name: /curation draft/i});

      expect(within(draftSection()).getByText(/From the All Projects widget/)).toHaveTextContent(
        'From the All Projects widget: 1 project added to the curation draft (1 in total). ' +
          '1 project from the All Projects widget is no longer listed.',
      );
      await waitFor(() => expect(window.location.hash).toBe(''));
    });

    it('finds a handed-over current project as the archive row that stands in for it once its semester is archived', async () => {
      const standIn = makeRow({id: ID_ARCHIVE, catalog: 'archive', current_project_id: ID_CURRENT});
      // The widget's draft may hold both ids of that project; it is still one project.
      window.history.replaceState(null, '', `/all-projects#curation-draft=${ID_CURRENT},${ID_ARCHIVE}`);
      render(builder({rows: [standIn]}));
      await screen.findByRole('heading', {level: 2, name: /curation draft/i});

      expect(mockHydrateProjectGridRowsSettled.mock.calls[0][0].map((row: ProjectGridRow) => row.id)).toEqual([
        ID_ARCHIVE,
      ]);
      expect(within(draftSection()).getByText(/From the All Projects widget/)).toHaveTextContent(
        /^From the All Projects widget: 1 project added to the curation draft \(1 in total\)\.$/,
      );
    });

    it('says so under the search tables when none of the handed-over projects are listed', () => {
      window.history.replaceState(null, '', `/all-projects#curation-draft=${ID_GONE}`);
      render(builder());

      expect(screen.getByText('1 project from the All Projects widget is no longer listed.')).toHaveAttribute(
        'role',
        'status',
      );
    });
  });
});
