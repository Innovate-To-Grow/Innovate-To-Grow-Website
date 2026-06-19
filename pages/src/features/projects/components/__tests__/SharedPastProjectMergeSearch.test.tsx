import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {SharedPastProjectMergeSearch} from '../SharedPastProjectMergeSearch';
import type {ProjectGridRow} from '../projectGrid';
import type {ProjectTableRow} from '@/features/projects/api';

const mockUseAuth = vi.fn();
const mockSearchPastProjectsWithAI = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

vi.mock('@/features/projects/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/projects/api')>();
  return {
    ...actual,
    searchPastProjectsWithAI: (...args: unknown[]) => mockSearchPastProjectsWithAI(...args),
  };
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

const makeProjectTableRow = (overrides: Partial<ProjectTableRow>): ProjectTableRow => ({
  id: 'project-1',
  semester_label: '2024-1 Spring',
  class_code: 'CAP',
  team_number: '501',
  team_name: 'AI Team',
  project_title: 'AI Selected Project',
  organization: 'AI Org',
  industry: 'Energy',
  abstract: 'AI selected project details.',
  student_names: 'Alex Student',
  track: null,
  presentation_order: null,
  ...overrides,
});

const alphaRow = makeRow({team_number: 'T01', team_name: 'Team Alpha', project_title: 'Alpha Project'});
const bravoRow = makeRow({team_number: 'T02', team_name: 'Team Bravo', project_title: 'Bravo Project'});
const charlieRow = makeRow({team_number: 'T03', team_name: 'Team Charlie', project_title: 'Charlie Project'});

describe('SharedPastProjectMergeSearch', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue({isAuthenticated: true});
    mockSearchPastProjectsWithAI.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('uses the search table merge flow to add selected projects', async () => {
    const onAddRows = vi.fn().mockResolvedValue(undefined);

    render(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow, charlieRow]}
        onAddRows={onAddRows}
      />,
    );

    expect(screen.getByRole('heading', {level: 2, name: 'Add Projects from Full Archive'})).toBeInTheDocument();
    expect(screen.getByText('More help: buttons, saving & tables')).toBeInTheDocument();
    expect(screen.getAllByRole('button', {name: 'Add Selected'}).length).toBeGreaterThan(0);
    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    expect(screen.queryByText('Alpha Project')).toBeNull();
    expect(screen.getAllByText('Bravo Project').length).toBeGreaterThan(0);

    // The per-table merge button adds the checked rows directly — there is no confirmation dialog.
    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /add selected/i}));

    await waitFor(() => {
      expect(onAddRows).toHaveBeenCalledWith([
        expect.objectContaining({
          project_title: 'Bravo Project',
          semester_label: '2025 Spring',
        }),
      ]);
    });
    expect(await screen.findByText('1 project added.')).toBeInTheDocument();
  });

  it('can refresh a full-archive standard search table without deleting it', () => {
    const onRefreshRows = vi.fn();
    const onAddRows = vi.fn();

    const {rerender} = render(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow, charlieRow]}
        onAddRows={onAddRows}
        onRefreshRows={onRefreshRows}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /refresh search table/i}));

    expect(onRefreshRows).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    expect(screen.getByText(/Refreshing this full-archive search table/i)).toBeInTheDocument();

    // The refetch resolves with a new archive snapshot; the table picks up the new project.
    const deltaRow = makeRow({team_number: 'T04', team_name: 'Team Delta', project_title: 'Delta Project'});
    rerender(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow, charlieRow, deltaRow]}
        onAddRows={onAddRows}
        onRefreshRows={onRefreshRows}
      />,
    );

    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    expect(screen.getAllByText('Delta Project').length).toBeGreaterThan(0);
    expect(screen.getByText('Search table refreshed from the latest past-project archive.')).toBeInTheDocument();
  });

  it('adds AI results as a selectable AI Search Table and submits checked rows', async () => {
    const onAddRows = vi.fn().mockResolvedValue(undefined);
    const aiProject = makeProjectTableRow({
      project_title: 'Solar Pump Station',
      team_number: '501',
      team_name: 'Solar Search',
      organization: 'Water District',
      industry: 'Water',
    });
    const expectedGridRow = makeRow({
      id: 'project-1',
      semester_label: '2024 Spring',
      class_code: 'CAP',
      team_number: '501',
      team_name: 'Solar Search',
      project_title: 'Solar Pump Station',
      organization: 'Water District',
      industry: 'Water',
      abstract: 'AI selected project details.',
      student_names: 'Alex Student',
    });
    mockSearchPastProjectsWithAI.mockResolvedValue({
      available: true,
      query: 'solar pump',
      results: [aiProject],
      usage: {inputTokens: 8, outputTokens: 2, totalTokens: 10},
    });

    render(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow, charlieRow]}
        onAddRows={onAddRows}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    expect(screen.getByRole('heading', {level: 3, name: 'AI Search Table'})).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/ask ai to find relevant past projects/i), {
      target: {value: 'solar pump'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByRole('heading', {level: 3, name: 'AI Search Table: solar pump'})).toBeInTheDocument();
    expect(mockSearchPastProjectsWithAI).toHaveBeenCalledWith('solar pump', 10);

    const aiTable = screen
      .getByRole('heading', {level: 3, name: 'AI Search Table: solar pump'})
      .closest('section') as HTMLElement;
    fireEvent.click((await within(aiTable).findAllByLabelText('Select Solar Pump Station'))[0]);
    await waitFor(() => expect(within(aiTable).getByRole('button', {name: /add selected/i})).toBeEnabled());
    fireEvent.click(within(aiTable).getByRole('button', {name: /add selected/i}));

    await waitFor(() => {
      expect(onAddRows).toHaveBeenCalledWith([expectedGridRow]);
    });
  });

  it('shows the AI loading marquee on the search form instead of the controls status box', async () => {
    let resolveSearch: (value: Awaited<ReturnType<typeof mockSearchPastProjectsWithAI>>) => void = () => {};
    mockSearchPastProjectsWithAI.mockReturnValue(
      new Promise((resolve) => {
        resolveSearch = resolve;
      }),
    );

    render(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow, charlieRow]}
        onAddRows={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask ai to find relevant past projects/i), {
      target: {value: 'solar pump'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    const aiSearchForm = screen.getByPlaceholderText(/ask ai to find relevant past projects/i).closest('form');
    const aiSearchInputFrame = screen
      .getByPlaceholderText(/ask ai to find relevant past projects/i)
      .closest('.past-projects-ai-search-input-frame');
    expect(aiSearchForm).toHaveClass('past-projects-ai-search', 'is-loading');
    expect(aiSearchForm).toHaveAttribute('aria-busy', 'true');
    expect(aiSearchInputFrame).not.toBeNull();
    expect(screen.getByRole('status')).toHaveTextContent('Searching past projects with AI...');
    expect(document.querySelector('.past-projects-ai-search-spinner')).toBeNull();
    expect(document.querySelector('.past-projects-ai-search-progress')).toBeNull();
    expect(screen.getByText('Searching past projects with AI...').closest('.project-grid-controls-status')).toBeNull();

    resolveSearch({
      available: true,
      query: 'solar pump',
      results: [
        makeProjectTableRow({
          project_title: 'Solar Pump Station',
          team_number: '501',
          team_name: 'Solar Search',
          organization: 'Water District',
          industry: 'Water',
        }),
      ],
      usage: {inputTokens: 8, outputTokens: 2, totalTokens: 10},
    });

    expect(await screen.findByRole('heading', {level: 3, name: 'AI Search Table: solar pump'})).toBeInTheDocument();
  });

  it('does not add an empty AI table when all AI matches already exist in the shared result', async () => {
    const onAddRows = vi.fn().mockResolvedValue(undefined);
    const formattedAlphaRow = {...alphaRow, semester_label: '2025 Spring'};
    mockSearchPastProjectsWithAI.mockResolvedValue({
      available: true,
      query: 'alpha',
      results: [
        makeProjectTableRow({
          semester_label: '2025-1 Spring',
          class_code: alphaRow.class_code,
          team_number: alphaRow.team_number,
          team_name: alphaRow.team_name,
          project_title: alphaRow.project_title,
          organization: alphaRow.organization,
          industry: alphaRow.industry,
          abstract: alphaRow.abstract,
          student_names: alphaRow.student_names,
        }),
      ],
      usage: {inputTokens: 8, outputTokens: 2, totalTokens: 10},
    });

    render(
      <SharedPastProjectMergeSearch
        currentRows={[formattedAlphaRow]}
        error={null}
        loading={false}
        rows={[formattedAlphaRow, bravoRow]}
        onAddRows={onAddRows}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask ai to find relevant past projects/i), {
      target: {value: 'alpha'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByText('AI found projects that are already in this shared result.')).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 3, name: 'AI Search Table'})).toBeInTheDocument();
    expect(onAddRows).not.toHaveBeenCalled();
  });

  it('allows only one AI Search Table in the shared add-projects flow', () => {
    render(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow, charlieRow]}
        onAddRows={vi.fn()}
      />,
    );

    const addAIButton = screen.getByRole('button', {name: /\+ ai search table/i});
    expect(addAIButton).toBeEnabled();

    fireEvent.click(addAIButton);

    expect(screen.getByRole('heading', {level: 3, name: 'AI Search Table'})).toBeInTheDocument();
    expect(addAIButton).toBeDisabled();
    expect(screen.getAllByRole('heading', {level: 3, name: /ai search table/i})).toHaveLength(1);
  });

  it('does not number the only standard Search Table when an AI Search Table is also open', () => {
    render(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow, charlieRow]}
        onAddRows={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));

    expect(screen.getByRole('heading', {level: 3, name: 'Search Table'})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {level: 3, name: 'Search Table 1'})).toBeNull();
    expect(screen.getByRole('heading', {level: 3, name: 'AI Search Table'})).toBeInTheDocument();
  });

  it('shows a sign-in dialog when a signed-out visitor clicks the AI Search Table button', () => {
    mockUseAuth.mockReturnValue({isAuthenticated: false});

    render(
      <SharedPastProjectMergeSearch
        currentRows={[alphaRow]}
        error={null}
        loading={false}
        rows={[alphaRow, bravoRow, charlieRow]}
        onAddRows={vi.fn()}
      />,
    );

    const addAIButton = screen.getByRole('button', {name: /\+ ai search table/i});
    expect(addAIButton).toBeEnabled();
    expect(addAIButton).toHaveAttribute('aria-disabled', 'true');
    expect(addAIButton).toHaveClass('is-login-required');

    fireEvent.click(addAIButton);

    expect(screen.getByRole('dialog', {name: /sign in required/i})).toBeInTheDocument();
    expect(screen.getByText('You need to sign in before using AI search.')).toBeInTheDocument();
    expect(mockSearchPastProjectsWithAI).not.toHaveBeenCalled();
  });
});
