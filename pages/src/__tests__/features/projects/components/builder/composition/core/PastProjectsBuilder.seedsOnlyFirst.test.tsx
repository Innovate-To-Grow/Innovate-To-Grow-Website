import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/builder/composition/PastProjectsBuilder';
import {authenticatedAuth, makeRow, ROWS} from '@/__tests__/features/projects/components/builder/composition/fixtures/pastProjectsBuilderFixtures';

const mockUseAuth = vi.fn();
const mockSearchPastProjectsWithAI = vi.fn();
const mockBuildLoginPath = vi.fn();
const mockHydrateProjectGridRowsSettled = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

vi.mock('@/features/auth/api/navigation/redirects', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth/api/navigation/redirects')>();
  return {
    ...actual,
    buildLoginPath: (...args: unknown[]) => mockBuildLoginPath(...args),
  };
});

vi.mock('@/features/projects/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/projects/api')>();
  return {
    ...actual,
    searchPastProjectsWithAI: (...args: unknown[]) => mockSearchPastProjectsWithAI(...args),
    hydrateProjectGridRowsSettled: (...args: unknown[]) => mockHydrateProjectGridRowsSettled(...args),
  };
});

describe('PastProjectsBuilder — Save/Merge selection contract', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue(authenticatedAuth);
    mockSearchPastProjectsWithAI.mockReset();
    mockBuildLoginPath.mockReset();
    mockHydrateProjectGridRowsSettled.mockReset();
    // The builder keeps its draft in localStorage; clear it so drafts don't leak between tests.
    localStorage.clear();
    sessionStorage.clear();
    vi.spyOn(window, 'confirm').mockImplementation(() => {
      throw new Error('Past projects should use an in-page confirmation dialog.');
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('seeds only the first search table with the search it was given', () => {
    render(
      <PastProjectsBuilder rows={ROWS} loading={false} error={null} initialSearch="Bravo" onCreateShare={vi.fn()} />,
    );

    const table = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
    expect(within(table).getByRole('searchbox')).toHaveValue('Bravo');

    fireEvent.click(screen.getByRole('button', {name: '+ Search Table'}));
    const table2 = screen.getByRole('heading', {level: 3, name: 'Search Table 2'}).closest('section') as HTMLElement;
    expect(within(table2).getByRole('searchbox')).toHaveValue('');
  });

  it('heads the search tables with a section title and its add buttons', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const section = screen.getByRole('region', {name: 'Search Tables'});
    const addGroup = within(section).getByRole('group', {name: 'Add a table'});
    expect(within(addGroup).getAllByRole('button').map((button) => button.textContent)).toEqual([
      '+ Search Table',
      '+ AI Search Table',
    ]);
    expect(within(section).getByText('Help: Buttons, Saving and Tables')).toBeInTheDocument();
    // The embed's "Section titles" option hides the heading by this marker (visually only: it stays a heading).
    expect(within(section).getByRole('heading', {level: 2, name: 'Search Tables'})).toHaveAttribute(
      'data-embed-section',
      'section-title',
    );
  });

  it('says in its help that tables share one archive and that Refresh starts a table over', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const help = screen.getByText('Help: Buttons, Saving and Tables').closest('details') as HTMLElement;
    expect(help).toHaveTextContent('Adds another search table over the same past-project archive');
    expect(help).not.toHaveTextContent('loads the full past-project archive on its own');
    expect(help).toHaveTextContent(
      'Refresh Search Table reloads the archive and starts that table over: its search, sort, Per page, ' +
        'checked rows and tidy edits are cleared.',
    );
    // Button names in Title Case, in bold like the help's other button names.
    expect(within(help).getByText('Delete Table', {selector: 'dt'})).toBeInTheDocument();
    expect(within(help).getByText('Delete Table', {selector: 'dd strong'})).toBeInTheDocument();
  });

  it('omits the search table number until there are multiple tables', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {level: 3, name: 'Search Table 1'})).toBeNull();
    expect(screen.queryByRole('button', {name: /delete table/i})).toBeNull();

    fireEvent.click(screen.getByRole('button', {name: /\+ search table/i}));

    expect(screen.queryByRole('heading', {level: 3, name: 'Search Table'})).toBeNull();
    expect(screen.getByRole('heading', {level: 3, name: 'Search Table 1'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 3, name: 'Search Table 2'})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: /delete table: search table 1/i})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: /delete table: search table 2/i})).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: /delete table: search table 1/i}));

    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {level: 3, name: 'Search Table 2'})).toBeNull();
    expect(screen.queryByRole('button', {name: /delete table/i})).toBeNull();
  });

  it('does not number the only standard Search Table when an AI Search Table is also open', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));

    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {level: 3, name: 'Search Table 1'})).toBeNull();
    expect(screen.getByRole('heading', {level: 3, name: 'AI Search Table'})).toBeInTheDocument();
  });

  it('ignores a rows change when no refresh was requested', () => {
    const onRefreshRows = vi.fn();
    const {rerender} = render(
      <PastProjectsBuilder
        rows={ROWS}
        loading={false}
        error={null}
        onRefreshRows={onRefreshRows}
        onCreateShare={vi.fn()}
      />,
    );

    rerender(
      <PastProjectsBuilder
        rows={[...ROWS, makeRow({team_number: 'T04', team_name: 'Team Delta', project_title: 'Delta Project'})]}
        loading={false}
        error={null}
        onRefreshRows={onRefreshRows}
        onCreateShare={vi.fn()}
      />,
    );

    expect(onRefreshRows).not.toHaveBeenCalled();
    expect(screen.queryByText('Delta Project')).toBeNull();
  });

  it('navigates to login when the sign-in dialog is confirmed', () => {
    mockUseAuth.mockReturnValue({isAuthenticated: false});

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: 'AI Search Table'}));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: /sign in/i}));

    expect(mockBuildLoginPath).toHaveBeenCalled();
  });
});
