import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/builder/composition/PastProjectsBuilder';
import {authenticatedAuth, getMergedSection, ROWS} from '@/__tests__/features/projects/components/builder/composition/fixtures/pastProjectsBuilderFixtures';
import {makeProjectTableRow} from '@/__tests__/features/projects/components/builder/composition/aiSearch/pastProjectsBuilderAiSearchFixtures';

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
    const aiSearchInput = screen.getByPlaceholderText(/ask about past projects/i);
    expect(aiSearchInput.closest('.project-grid-controls-row')).not.toBeNull();
    expect(aiSearchInput.closest('.past-projects-action-bar')).toBeNull();

    fireEvent.change(aiSearchInput, {
      target: {value: 'solar sensors'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByRole('heading', {level: 3, name: 'AI Search Table: solar sensors'})).toBeInTheDocument();
    expect(mockSearchPastProjectsWithAI).toHaveBeenCalledWith('solar sensors', 10, 'past');

    const aiTable = screen
      .getByRole('heading', {level: 3, name: 'AI Search Table: solar sensors'})
      .closest('section') as HTMLElement;
    fireEvent.click((await within(aiTable).findAllByLabelText('Select Solar Sensor Platform'))[0]);
    await waitFor(() => expect(within(aiTable).getByRole('button', {name: /add to curation/i})).toBeEnabled());
    fireEvent.click(within(aiTable).getByRole('button', {name: /add to curation/i}));

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
    fireEvent.change(screen.getByPlaceholderText(/ask about past projects/i), {
      target: {value: 'solar sensors'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    const aiSearchForm = screen.getByPlaceholderText(/ask about past projects/i).closest('form');
    const aiSearchInputFrame = screen
      .getByPlaceholderText(/ask about past projects/i)
      .closest('.past-projects-ai-search-input-frame');
    expect(aiSearchForm).toHaveClass('past-projects-ai-search', 'is-loading');
    expect(aiSearchForm).toHaveAttribute('aria-busy', 'true');
    expect(aiSearchInputFrame).not.toBeNull();
    expect(within(aiSearchForm as HTMLElement).getByRole('status')).toHaveTextContent('Searching past projects with AI…');
    // The site's loading indicator, inside the form's own status line.
    expect(
      within(aiSearchForm as HTMLElement).getByRole('status').querySelector('.loading-indicator-spinner'),
    ).toHaveAttribute('aria-hidden', 'true');
    expect(document.querySelector('.past-projects-ai-search-spinner')).toBeNull();
    expect(document.querySelector('.past-projects-ai-search-progress')).toBeNull();
    expect(screen.getByText('Searching past projects with AI…').closest('.project-grid-controls-status')).toBeNull();
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
    expect(screen.queryByPlaceholderText(/ask about past projects/i)).toBeNull();
  });
});
