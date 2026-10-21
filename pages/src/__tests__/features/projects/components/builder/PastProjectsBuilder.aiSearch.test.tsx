import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/PastProjectsBuilder';
import type {ProjectGridRow} from '@/features/projects/components/projectGrid';
import type {ProjectTableRow} from '@/features/projects/api';

const mockUseAuth = vi.fn();
const mockSearchPastProjectsWithAI = vi.fn();
const mockBuildLoginPath = vi.fn();
const mockHydrateProjectGridRowsSettled = vi.fn();
const authenticatedAuth = {
  isAuthenticated: true,
  isInitializing: false,
  unverified: false,
  user: {member_uuid: 'member-1', email: 'member@example.com'},
};

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

vi.mock('@/features/auth/api/redirects', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth/api/redirects')>();
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
  team_number: '101',
  team_name: 'Solar Team',
  project_title: 'Solar Project',
  organization: 'Solar Org',
  industry: 'Energy',
  abstract: 'A solar project abstract.',
  student_names: 'Alex Student',
  track: null,
  presentation_order: null,
  ...overrides,
});

const ROWS: ProjectGridRow[] = [
  makeRow({team_number: 'T01', team_name: 'Team Alpha', project_title: 'Alpha Project'}),
  makeRow({team_number: 'T02', team_name: 'Team Bravo', project_title: 'Bravo Project'}),
  makeRow({team_number: 'T03', team_name: 'Team Charlie', project_title: 'Charlie Project'}),
];

const getMergedSection = () => {
  const heading = screen.queryByRole('heading', {name: /saved merged results/i});
  return heading ? (heading.closest('section') as HTMLElement) : null;
};

describe('PastProjectsBuilder — AI search table', () => {
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

  it('adds AI results as a selectable AI Search Table and merges checked rows', async () => {
    mockSearchPastProjectsWithAI.mockResolvedValue({
      available: true,
      query: 'solar sensors',
      results: [
        makeProjectTableRow({
          id: 'ai-project-1',
          project_title: 'Solar Sensor Platform',
          team_number: '201',
        }),
      ],
      usage: {inputTokens: 10, outputTokens: 2, totalTokens: 12},
    });

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    expect(screen.getByRole('heading', {level: 3, name: 'AI Search Table'})).toBeInTheDocument();
    const aiSearchInput = screen.getByPlaceholderText(/ask ai to find relevant past projects/i);
    expect(aiSearchInput.closest('.project-grid-controls-row')).not.toBeNull();
    expect(aiSearchInput.closest('.past-projects-action-bar')).toBeNull();

    fireEvent.change(aiSearchInput, {
      target: {value: 'solar sensors'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByRole('heading', {level: 3, name: 'AI Search Table: solar sensors'})).toBeInTheDocument();
    expect(mockSearchPastProjectsWithAI).toHaveBeenCalledWith('solar sensors', 10);

    const aiTable = screen
      .getByRole('heading', {level: 3, name: 'AI Search Table: solar sensors'})
      .closest('section') as HTMLElement;
    fireEvent.click((await within(aiTable).findAllByLabelText('Select Solar Sensor Platform'))[0]);
    await waitFor(() => expect(within(aiTable).getByRole('button', {name: /save selected/i})).toBeEnabled());
    fireEvent.click(within(aiTable).getByRole('button', {name: /save selected/i}));

    const merged = getMergedSection();
    expect(merged).not.toBeNull();
    expect(within(merged as HTMLElement).getAllByText('Solar Sensor Platform').length).toBeGreaterThan(0);
  });

  it('shows AI search progress while the request is running', async () => {
    let resolveSearch: (value: Awaited<ReturnType<typeof mockSearchPastProjectsWithAI>>) => void = () => {};
    mockSearchPastProjectsWithAI.mockReturnValue(
      new Promise((resolve) => {
        resolveSearch = resolve;
      }),
    );

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask ai to find relevant past projects/i), {
      target: {value: 'solar sensors'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    const aiSearchForm = screen.getByPlaceholderText(/ask ai to find relevant past projects/i).closest('form');
    const aiSearchInputFrame = screen
      .getByPlaceholderText(/ask ai to find relevant past projects/i)
      .closest('.past-projects-ai-search-input-frame');
    expect(aiSearchForm).toHaveClass('past-projects-ai-search', 'is-loading');
    expect(aiSearchForm).toHaveAttribute('aria-busy', 'true');
    expect(aiSearchInputFrame).not.toBeNull();
    expect(within(aiSearchForm as HTMLElement).getByRole('status')).toHaveTextContent('Searching past projects with AI...');
    expect(document.querySelector('.past-projects-ai-search-spinner')).toBeNull();
    expect(document.querySelector('.past-projects-ai-search-progress')).toBeNull();
    expect(screen.getByText('Searching past projects with AI...').closest('.project-grid-controls-status')).toBeNull();
    expect(screen.getByRole('button', {name: 'Search'})).toBeDisabled();
    expect(screen.queryByText('Searching...')).toBeNull();

    resolveSearch({
      available: true,
      query: 'solar sensors',
      results: [
        makeProjectTableRow({
          id: 'ai-project-1',
          project_title: 'Solar Sensor Platform',
          team_number: '201',
        }),
      ],
      usage: {inputTokens: 10, outputTokens: 2, totalTokens: 12},
    });

    expect(await screen.findByRole('heading', {level: 3, name: 'AI Search Table: solar sensors'})).toBeInTheDocument();
  });

  it('does not call AI search when the visitor is signed out', () => {
    mockUseAuth.mockReturnValue({isAuthenticated: false});

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const addAIButton = screen.getByRole('button', {name: 'AI Search Table'});
    expect(screen.queryByText('Sign in to use AI search.')).toBeNull();
    // A lock and a note say why, instead of the "+".
    expect(addAIButton).toHaveAccessibleDescription('AI Search Table needs you to sign in.');
    expect(addAIButton.querySelector('svg')).not.toBeNull();
    expect(addAIButton).toBeEnabled();
    expect(addAIButton).not.toHaveAttribute('aria-disabled');
    expect(addAIButton).toHaveClass('is-login-required');
    fireEvent.click(addAIButton);

    expect(screen.getByRole('dialog', {name: /sign in required/i})).toBeInTheDocument();
    expect(screen.getByText('You need to sign in before using AI search.')).toBeInTheDocument();
    expect(mockSearchPastProjectsWithAI).not.toHaveBeenCalled();
    expect(screen.queryByPlaceholderText(/ask ai to find relevant past projects/i)).toBeNull();
  });

  it('shows unavailable AI search responses inline inside the AI table', async () => {
    mockSearchPastProjectsWithAI.mockResolvedValue({
      available: false,
      message: 'AI search is not configured yet.',
      query: 'solar',
      results: [],
      usage: {},
    });

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask ai to find relevant past projects/i), {
      target: {value: 'solar'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect((await screen.findByText('AI search is not configured yet.')).closest('.past-projects-ai-search-message')).toHaveClass(
      'past-projects-ai-search-message',
      'is-error',
    );
    expect(screen.getByRole('heading', {level: 3, name: 'AI Search Table'})).toBeInTheDocument();
  });

  it('allows only one AI Search Table at a time', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const addAIButton = screen.getByRole('button', {name: /\+ ai search table/i});
    expect(addAIButton).toBeEnabled();

    fireEvent.click(addAIButton);

    expect(screen.getByRole('heading', {level: 3, name: 'AI Search Table'})).toBeInTheDocument();
    expect(addAIButton).toBeDisabled();
    expect(screen.getAllByRole('heading', {level: 3, name: /ai search table/i})).toHaveLength(1);
  });

  it('shows a no-results message when AI search finds nothing', async () => {
    mockSearchPastProjectsWithAI.mockResolvedValue({
      available: true,
      query: 'solar',
      results: [],
      usage: {},
    });

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask ai to find relevant past projects/i), {
      target: {value: 'solar'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByText('AI search did not find matching past projects.')).toBeInTheDocument();
  });

  it('shows the API detail when an AI search rejects', async () => {
    mockSearchPastProjectsWithAI.mockRejectedValue({response: {data: {detail: 'AI backend down.'}}});

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask ai to find relevant past projects/i), {
      target: {value: 'solar'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByText('AI backend down.')).toBeInTheDocument();
  });

  it('shows the message field when an AI search rejects without a detail', async () => {
    mockSearchPastProjectsWithAI.mockRejectedValue({response: {data: {message: 'Try later.'}}});

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask ai to find relevant past projects/i), {
      target: {value: 'solar'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByText('Try later.')).toBeInTheDocument();
  });
});
