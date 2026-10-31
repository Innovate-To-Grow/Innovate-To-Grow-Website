import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/builder/composition/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

// Where keyboard focus goes after the builder's actions. Browsers blur a focused button that turns `disabled` or
// leaves the page, which dropped keyboard users to <body>; jsdom does neither, so these tests check what the
// builder does about it: buttons stay focusable (aria-disabled), and focus is moved on purpose.

const mockUseAuth = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {...actual, useAuth: () => mockUseAuth()};
});

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

const ROWS: ProjectGridRow[] = [
  makeRow({team_number: 'T01', team_name: 'Team Alpha', project_title: 'Alpha Project'}),
  makeRow({team_number: 'T02', team_name: 'Team Bravo', project_title: 'Bravo Project'}),
  makeRow({team_number: 'T03', team_name: 'Team Charlie', project_title: 'Charlie Project'}),
];

const press = (button: HTMLElement) => {
  button.focus();
  fireEvent.click(button);
};

const searchTable = (title = 'Search Table') =>
  screen.getByRole('heading', {level: 3, name: title}).closest('[data-search-table-id]') as HTMLElement;

const draftCard = () => screen.getByRole('heading', {level: 2, name: 'Curation Draft'}).closest('section') as HTMLElement;

const desktopTable = (container: HTMLElement) => container.querySelector('.project-grid-table-wrap') as HTMLElement;

const renderBuilder = () =>
  render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onRefreshRows={vi.fn()} onCreateShare={vi.fn()} />);

/** Checks the named projects in the first search table and adds them to the draft. */
const addToDraft = (...titles: string[]) => {
  const table = within(desktopTable(searchTable()));
  titles.forEach((title) => fireEvent.click(table.getByLabelText(`Select ${title}`)));
  fireEvent.click(within(searchTable()).getByRole('button', {name: /add to curation/i}));
};

describe('PastProjectsBuilder — keyboard focus after its actions', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isInitializing: false,
      unverified: false,
      user: {member_uuid: 'member-1', email: 'member@example.com'},
    });
    localStorage.clear();
    sessionStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('keeps the tidy and selection buttons focusable when their own press leaves them nothing to do', () => {
    renderBuilder();
    const table = within(searchTable());
    const deselect = table.getByRole('button', {name: 'Deselect'});
    const removeFromTable = table.getByRole('button', {name: 'Remove from Table'});
    const undoRowChange = table.getByRole('button', {name: 'Undo Row Change'});

    // Unavailable but reachable, and they say what makes them available.
    for (const button of [deselect, removeFromTable]) {
      expect(button).not.toBeDisabled();
      expect(button).toHaveAttribute('aria-disabled', 'true');
      expect(button).toHaveAccessibleDescription('Check one or more rows in the table first.');
    }

    fireEvent.click(within(desktopTable(searchTable())).getByLabelText('Select Bravo Project'));
    expect(removeFromTable).not.toHaveAttribute('aria-disabled');
    press(removeFromTable);
    expect(screen.queryAllByText('Bravo Project')).toHaveLength(0);
    expect(removeFromTable).toHaveFocus();
    expect(removeFromTable).toHaveAttribute('aria-disabled', 'true');

    press(undoRowChange);
    expect(screen.getAllByText('Bravo Project').length).toBeGreaterThan(0);
    expect(undoRowChange).toHaveFocus();
    expect(undoRowChange).toHaveAttribute('aria-disabled', 'true');
    // A press while unavailable does nothing.
    fireEvent.click(undoRowChange);
    expect(screen.getAllByText('Bravo Project').length).toBeGreaterThan(0);

    fireEvent.click(within(desktopTable(searchTable())).getByLabelText('Select Alpha Project'));
    press(deselect);
    expect(deselect).toHaveFocus();
    expect(deselect).toHaveAttribute('aria-disabled', 'true');
  });

  it('keeps Add to Curation focusable once the save has unchecked the rows it took', () => {
    renderBuilder();
    fireEvent.click(within(desktopTable(searchTable())).getByLabelText('Select Alpha Project'));
    const addButton = within(searchTable()).getByRole('button', {name: /add to curation/i});

    press(addButton);

    expect(within(draftCard()).getAllByText('Alpha Project').length).toBeGreaterThan(0);
    expect(addButton).not.toBeDisabled();
    expect(addButton).toHaveAttribute('aria-disabled', 'true');
    expect(addButton).toHaveFocus();
  });

  it("moves focus to a new table's search field, and to the neighbouring table's heading after Delete table", () => {
    renderBuilder();

    press(screen.getByRole('button', {name: '+ Search Table'}));
    const secondTable = searchTable('Search Table 2');
    expect(within(secondTable).getByRole('searchbox')).toHaveFocus();

    press(within(secondTable).getByRole('button', {name: 'Delete table: Search Table 2'}));
    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toHaveFocus();
  });

  it("moves focus to the AI table's search field when it is added", () => {
    renderBuilder();

    press(screen.getByRole('button', {name: '+ AI Search Table'}));

    const aiTable = screen.getByRole('heading', {level: 3, name: 'AI Search Table'}).closest('[data-search-table-id]') as HTMLElement;
    expect(within(aiTable).getByLabelText('AI Search')).toHaveFocus();
  });

  it("moves focus to the next draft row's Remove after one is removed, then to the draft's heading", () => {
    renderBuilder();
    addToDraft('Alpha Project', 'Bravo Project');
    // The draft's table (gone once it has no rows).
    const draftRows = () => {
      const table = desktopTable(draftCard());
      return table ? within(table).queryAllByRole('button', {name: /^remove/i}) : [];
    };
    expect(draftRows()).toHaveLength(2);

    press(draftRows()[0]);
    expect(draftRows()).toHaveLength(1);
    expect(draftRows()[0]).toHaveFocus();

    press(draftRows()[0]);
    expect(draftRows()).toHaveLength(0);
    expect(screen.getByRole('heading', {level: 2, name: 'Curation Draft'})).toHaveFocus();
  });

  it('keeps Remove Selected and Undo focusable, and returns focus to Clear Draft after its confirmation', () => {
    renderBuilder();
    addToDraft('Alpha Project', 'Bravo Project');
    const card = within(draftCard());
    fireEvent.click(within(desktopTable(draftCard())).getByLabelText('Select Alpha Project'));

    const removeSelected = card.getByRole('button', {name: 'Remove Selected'});
    press(removeSelected);
    expect(removeSelected).toHaveFocus();
    expect(removeSelected).toHaveAttribute('aria-disabled', 'true');

    const undo = card.getByRole('button', {name: 'Undo'});
    press(undo);
    expect(undo).toHaveFocus();
    expect(undo).toHaveAttribute('aria-disabled', 'true');

    const clearDraft = card.getByRole('button', {name: 'Clear Draft'});
    press(clearDraft);
    // The confirm is boxed red like the button that opened it; Cancel, the safe choice, has focus.
    const confirm = within(screen.getByRole('dialog')).getByRole('button', {name: 'Clear Draft'});
    expect(confirm).toHaveClass('itg-btn', 'itg-btn-outline', 'itg-btn-danger');
    expect(confirm).not.toHaveClass('itg-btn-primary');
    expect(within(screen.getByRole('dialog')).getByRole('button', {name: 'Cancel'})).toHaveFocus();
    fireEvent.click(confirm);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(clearDraft).toHaveFocus();
    expect(clearDraft).toHaveAttribute('aria-disabled', 'true');
  });
});
