import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/builder/composition/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

// The Past Projects widget on a partner's page runs in a cross-site frame whose storage the site's own tabs never
// see: sign-in and saving continue on the full page in a new tab, and the draft goes along in the link.

const mockUseAuth = vi.fn();
const mockHydrateProjectGridRowsSettled = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {...actual, useAuth: () => mockUseAuth()};
});

vi.mock('@/features/projects/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/projects/api')>();
  return {
    ...actual,
    hydrateProjectGridRowsSettled: (...args: unknown[]) => mockHydrateProjectGridRowsSettled(...args),
  };
});

const ID_ALPHA = '11111111-1111-4111-8111-111111111111';
const ID_BRAVO = '22222222-2222-4222-8222-222222222222';
const ID_GONE = '33333333-3333-4333-8333-333333333333';

const makeRow = (overrides: Partial<ProjectGridRow>): ProjectGridRow => ({
  semester_label: '2025-1 Spring',
  class_code: 'ENGR 120',
  team_number: 'T01',
  team_name: 'Team Alpha',
  project_title: 'Alpha Project',
  organization: 'Acme',
  industry: 'Technology',
  abstract: '',
  student_names: '',
  is_presenting: '',
  ...overrides,
});

// Compact archive rows, as the archive endpoint returns them: details load when they are added.
const ROWS: ProjectGridRow[] = [
  makeRow({id: ID_ALPHA, team_number: 'T01', project_title: 'Alpha Project'}),
  makeRow({id: ID_BRAVO, team_number: 'T02', team_name: 'Team Bravo', project_title: 'Bravo Project'}),
];

const DRAFT_STORAGE_KEY = 'past-projects:builder:draft';
const signedOut = {isAuthenticated: false, isInitializing: false, unverified: false, user: null};

const renderBuilder = (props: {rows?: ProjectGridRow[]; loading?: boolean} = {}) => (
  <PastProjectsBuilder rows={props.rows ?? ROWS} loading={props.loading ?? false} error={null} onCreateShare={vi.fn()} />
);

const draftSection = () => screen.getByRole('heading', {level: 2, name: /curation draft/i}).closest('section') as HTMLElement;

/** Checks the rows and adds them; their details load first, so the draft card shows a moment later. */
const addToCuration = async (...titles: string[]) => {
  for (const title of titles) {
    fireEvent.click(screen.getAllByLabelText(`Select ${title}`)[0]);
  }
  fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
  await screen.findByRole('heading', {level: 2, name: /curation draft/i});
};

describe('PastProjectsBuilder and the Past Projects widget', () => {
  beforeEach(() => {
    mockUseAuth.mockReset().mockReturnValue(signedOut);
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

  describe('in the widget', () => {
    const NEW_TAB_LINK_NAME = /^Continue in Past Projects\s*\(opens in a new tab\)$/;

    beforeEach(() => window.history.replaceState(null, '', '/_embed/test-past'));

    it('continues to the full page in a new tab, with the draft, instead of signing in inside the frame', async () => {
      render(renderBuilder());
      await addToCuration('Alpha Project', 'Bravo Project');

      const continueLinks = within(draftSection()).getAllByRole('link', {name: /continue in past projects/i});
      // The card's button and the save section's link; neither signs in inside the frame or returns to /_embed/.
      expect(continueLinks).toHaveLength(2);
      for (const link of continueLinks) {
        expect(link).toHaveAttribute('href', `/past-projects#curation-draft=${ID_ALPHA},${ID_BRAVO}`);
        expect(link).toHaveAttribute('target', '_blank');
        // The space before the hint is inside the visually hidden span, so the underline ends at "Projects".
        // Browsers keep it in the name (the span is positioned out of the line); jsdom drops it, hence \s*.
        expect(link).toHaveAccessibleName(NEW_TAB_LINK_NAME);
        expect(link.querySelector('.sr-only')).toHaveTextContent(/^ \(opens in a new tab\)$/, {normalizeWhitespace: false});
        expect(link.firstChild).toHaveProperty('textContent', 'Continue in Past Projects');
      }
      expect(within(draftSection()).queryByRole('link', {name: /sign in/i})).toBeNull();
      expect(draftSection().querySelector('a[href*="/login"]')).toBeNull();
      // Both are buttons; the save section's says what happens there, once.
      for (const link of continueLinks) expect(link).toHaveClass('itg-btn', 'itg-btn-primary');
      expect(
        within(draftSection()).getByText(
          'Sign in there to save this curation and get a link to share it. This draft goes with you.',
        ),
      ).toHaveClass('project-grid-share-actions-note');
    });

    it("offers AI search's sign-in on the full page, with the draft, as a link to a new tab", async () => {
      render(renderBuilder());
      await addToCuration('Alpha Project');
      vi.useFakeTimers();
      try {
        fireEvent.click(screen.getByRole('button', {name: 'AI Search Table'}));

        const dialog = screen.getByRole('dialog', {name: 'Sign in required'});
        const link = within(dialog).getByRole('link', {name: NEW_TAB_LINK_NAME});
        expect(link).toHaveAttribute('href', `/past-projects#curation-draft=${ID_ALPHA}`);
        expect(link).toHaveAttribute('target', '_blank');
        expect(within(dialog).queryByRole('button', {name: 'Sign In'})).toBeNull();

        // The link opens its tab first; the dialog closes after the click.
        fireEvent.click(link);
        expect(screen.getByRole('dialog', {name: 'Sign in required'})).toBeInTheDocument();
        act(() => vi.runAllTimers());
        expect(screen.queryByRole('dialog', {name: 'Sign in required'})).toBeNull();
      } finally {
        vi.useRealTimers();
      }
    });

    it('does not take a handover itself', () => {
      window.history.replaceState(null, '', `/_embed/test-past#curation-draft=${ID_ALPHA}`);
      render(renderBuilder());

      expect(screen.queryByRole('heading', {level: 2, name: /curation draft/i})).toBeNull();
      expect(window.location.hash).toBe(`#curation-draft=${ID_ALPHA}`);
    });
  });

  describe('on the full page', () => {
    it('adds the projects a widget handed over once the archive loads, then drops them from the address', async () => {
      window.history.replaceState({idx: 0}, '', `/past-projects?value=x#curation-draft=${ID_BRAVO},${ID_GONE}`);
      const {rerender} = render(renderBuilder({rows: [], loading: true}));
      expect(window.location.hash).not.toBe('');

      rerender(renderBuilder());
      const section = await screen.findByRole('heading', {level: 2, name: /curation draft/i});
      const draft = section.closest('section') as HTMLElement;

      expect(mockHydrateProjectGridRowsSettled).toHaveBeenCalledTimes(1);
      expect(mockHydrateProjectGridRowsSettled.mock.calls[0][0].map((row: ProjectGridRow) => row.id)).toEqual([ID_BRAVO]);
      expect(within(draft).getAllByText('Bravo Project').length).toBeGreaterThan(0);
      expect(within(draft).getByRole('status')).toHaveTextContent(
        'From the Past Projects widget: 1 project added to the curation draft (1 in total). ' +
          '1 project from the Past Projects widget is no longer in the archive.',
      );
      // The draft is stored by an effect, which can run after the DOM change findByRole saw.
      await waitFor(() => {
        const stored = JSON.parse(localStorage.getItem(DRAFT_STORAGE_KEY) ?? '{}') as {rows?: ProjectGridRow[]};
        expect(stored.rows?.map((row) => row.abstract)).toEqual(['Bravo Project abstract']);
      });
      // Gone from the address, so a reload or a copied link does not add them again; the router's state stays.
      expect(window.location.pathname + window.location.search + window.location.hash).toBe('/past-projects?value=x');
      expect(window.history.state).toEqual({idx: 0});
    });

    it('keeps the projects already in this browser\'s draft and adds each project once', async () => {
      localStorage.setItem(
        DRAFT_STORAGE_KEY,
        JSON.stringify({owner: null, rows: [{...ROWS[0], abstract: 'Kept'}], name: '', note: ''}),
      );
      window.history.replaceState(null, '', `/past-projects#curation-draft=${ID_ALPHA},${ID_BRAVO}`);
      render(renderBuilder());

      expect(await within(draftSection()).findByText(/From the Past Projects widget/)).toHaveTextContent(
        'From the Past Projects widget: 1 project added to the curation draft (2 in total). 1 project was already in the curation draft.',
      );
    });

    it('says so under the search tables when none of the handed-over projects are in the archive', () => {
      window.history.replaceState(null, '', `/past-projects#curation-draft=${ID_GONE}`);
      render(renderBuilder());

      expect(screen.queryByRole('heading', {level: 2, name: /curation draft/i})).toBeNull();
      expect(screen.getByText('1 project from the Past Projects widget is no longer in the archive.')).toHaveAttribute(
        'role',
        'status',
      );
      expect(window.location.hash).toBe('');
    });

    it('signs in from the draft and comes back to this page', async () => {
      window.history.replaceState(null, '', '/past-projects?value=solar');
      render(renderBuilder());
      await addToCuration('Alpha Project');

      // The card header's button and the save section's, the same link.
      const signInLinks = within(draftSection()).getAllByRole('link', {name: 'Sign In to Save'});
      expect(signInLinks).toHaveLength(2);
      for (const link of signInLinks) {
        expect(link).toHaveAttribute('href', `/login?returnTo=${encodeURIComponent('/past-projects?value=solar')}`);
      }
    });
  });
});
