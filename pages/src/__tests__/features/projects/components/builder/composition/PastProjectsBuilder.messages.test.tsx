import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/builder/composition/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

// Where the builder's messages appear, and that screen readers hear them: each in a live region kept in the page
// (one inserted together with its text is often not announced), next to the controls that caused it.

const mockUseAuth = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {...actual, useAuth: () => mockUseAuth()};
});

const makeRow = (team: string, title: string): ProjectGridRow => ({
  semester_label: '2025-1 Spring',
  class_code: 'ENGR 120',
  team_number: team,
  team_name: `Team ${team}`,
  project_title: title,
  organization: 'Acme',
  industry: 'Technology',
  abstract: '',
  student_names: '',
  is_presenting: '',
});

const ROWS = [makeRow('T01', 'Alpha Project'), makeRow('T02', 'Bravo Project')];

const searchTablesSection = () => screen.getByRole('region', {name: 'Search Tables'});
const searchTablesStatus = () =>
  within(searchTablesSection()).getAllByRole('status').find((element) => element.closest('[data-search-table-id]') === null)!;
const draftCard = () => screen.getByRole('region', {name: 'Curation Draft'});
const desktopTable = (container: HTMLElement) => container.querySelector('.project-grid-table-wrap') as HTMLElement;

const renderBuilder = (props: Partial<Parameters<typeof PastProjectsBuilder>[0]> = {}) =>
  render(
    <PastProjectsBuilder rows={ROWS} loading={false} error={null} onRefreshRows={vi.fn()} onCreateShare={vi.fn()} {...props} />,
  );

const addBothToDraft = () => {
  const table = within(desktopTable(searchTablesSection()));
  fireEvent.click(table.getByLabelText('Select Alpha Project'));
  fireEvent.click(table.getByLabelText('Select Bravo Project'));
  fireEvent.click(within(searchTablesSection()).getByRole('button', {name: /add to curation/i}));
};

describe('PastProjectsBuilder — status messages', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isInitializing: false,
      unverified: false,
      user: {member_uuid: 'member-1', email: 'member@example.com'},
    });
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
  });

  it("reports removing and restoring draft rows in the draft card's status line, not under the search tables", () => {
    renderBuilder();
    addBothToDraft();
    const cardStatus = within(draftCard()).getByRole('status');
    expect(cardStatus).toBeEmptyDOMElement();

    fireEvent.click(within(desktopTable(draftCard())).getAllByRole('button', {name: /^remove/i})[0]);
    expect(cardStatus).toHaveTextContent('Project removed from the curation draft.');
    expect(searchTablesStatus()).toBeEmptyDOMElement();

    fireEvent.click(within(draftCard()).getByRole('button', {name: 'Undo'}));
    expect(cardStatus).toHaveTextContent('Curation draft restored.');

    // The card's line sits right under its table, ahead of the curation's name and note.
    const saveSection = within(draftCard()).getByRole('heading', {name: 'Save this curation'});
    expect(cardStatus.compareDocumentPosition(saveSection) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('keeps the search tables\' status line in the page, and reports a refresh in it', () => {
    const onRefreshRows = vi.fn();
    renderBuilder({onRefreshRows});
    const status = searchTablesStatus();
    expect(status).toBeEmptyDOMElement();

    fireEvent.click(within(searchTablesSection()).getByRole('button', {name: 'Refresh Search Table'}));

    expect(onRefreshRows).toHaveBeenCalledTimes(1);
    expect(searchTablesStatus()).toBe(status);
    expect(status).toHaveTextContent('Refreshing this search table from the latest past-project archive...');
  });

  it('announces that the archive is loading', () => {
    renderBuilder({rows: [], loading: true});

    expect(within(searchTablesSection()).getByText('Loading past projects...')).toHaveAttribute('role', 'status');
  });
});
