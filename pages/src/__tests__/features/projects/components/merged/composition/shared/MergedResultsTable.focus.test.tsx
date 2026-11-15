import {useState} from 'react';
import {act, cleanup, fireEvent, render, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '@/features/projects/components/merged/composition/MergedResultsTable';
import {createProjectGridItems, type ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

const mockUseAuth = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {...actual, useAuth: () => mockUseAuth()};
});

const makeRow = (team: string, title: string): ProjectGridRow => ({
  semester_label: '2025 Spring',
  class_code: 'ENGR 120',
  team_number: team,
  team_name: `Team ${team}`,
  project_title: title,
  organization: 'Acme',
  industry: 'Technology',
  abstract: 'An abstract.',
  student_names: 'Alice, Bob',
  is_presenting: '',
});

const ROWS = [makeRow('T01', 'Alpha Project'), makeRow('T02', 'Bravo Project'), makeRow('T03', 'Charlie Project')];

/** The owner's shared page: a removal shows once its save has landed (or never, when it fails). */
const SharedPage = ({save}: {save: () => Promise<void>}) => {
  const [rows, setRows] = useState(() => createProjectGridItems(ROWS, 'shared'));
  return (
    <MergedResultsTable
      rows={rows}
      sharedMode
      editable
      title="Owner curation"
      onUpdateShare={async (nextRows) => {
        await save();
        setRows(createProjectGridItems(nextRows, `shared-${nextRows.length}`));
      }}
    />
  );
};

const removeButtons = () =>
  within(document.querySelector('.project-grid-table-wrap') as HTMLElement).getAllByRole('button', {name: /^remove/i});

describe('MergedResultsTable — focus after a shared page removes a row', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({isAuthenticated: true, isInitializing: false, unverified: false, user: null});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('stays on the pressed Remove while the save runs, then moves to the Remove of the row that took its place', async () => {
    let finishSave = () => {};
    render(<SharedPage save={() => new Promise<void>((resolve) => (finishSave = resolve))} />);
    expect(removeButtons()).toHaveLength(3);

    const pressed = removeButtons()[1];
    pressed.focus();
    fireEvent.click(pressed);
    expect(pressed).toHaveFocus();

    await act(async () => finishSave());

    expect(removeButtons()).toHaveLength(2);
    expect(removeButtons()[1]).toHaveFocus();
  });

  it('leaves focus where it is when the save fails and the row stays', async () => {
    render(<SharedPage save={() => Promise.reject(new Error('offline'))} />);

    const pressed = removeButtons()[0];
    pressed.focus();
    fireEvent.click(pressed);
    await act(async () => {});

    expect(removeButtons()).toHaveLength(3);
    expect(removeButtons()[0]).toHaveFocus();
  });
});
