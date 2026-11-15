import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/curation/builder/composition/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {
  addToCuration,
  type BuilderProps,
  draftSection,
  ID_ARCHIVE,
  ID_CURRENT,
  ID_GONE,
  inAllProjects,
  makeRow,
  ROWS,
  signedOut,
} from '@/__tests__/features/projects/components/curation/builder/composition/catalog/pastProjectsBuilderAllProjectsFixtures';

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
