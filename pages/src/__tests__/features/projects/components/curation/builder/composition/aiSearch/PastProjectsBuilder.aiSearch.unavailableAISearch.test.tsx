import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/curation/builder/composition/PastProjectsBuilder';
import {authenticatedAuth, ROWS} from '@/__tests__/features/projects/components/curation/builder/composition/fixtures/pastProjectsBuilderFixtures';
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

  it('shows unavailable AI search responses inline inside the AI table, in words meant for members', async () => {
    mockSearchPastProjectsWithAI.mockResolvedValue({
      available: false,
      // The API's text is for the site's administrators.
      message: 'AI search is not configured yet. Check the AWS Bedrock credentials and model settings.',
      query: 'solar',
      results: [],
      usage: {},
    });

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask about past projects/i), {
      target: {value: 'solar'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(
      (await screen.findByText(/AI search is not available on this site right now/)).closest(
        '.past-projects-ai-search-message',
      ),
    ).toHaveClass('past-projects-ai-search-message', 'is-error');
    expect(screen.queryByText(/Bedrock/)).toBeNull();
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
    fireEvent.change(screen.getByPlaceholderText(/ask about past projects/i), {
      target: {value: 'solar'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByText('AI search did not find matching past projects.')).toBeInTheDocument();
  });

  it('shows the API detail when an AI search rejects', async () => {
    mockSearchPastProjectsWithAI.mockRejectedValue({response: {data: {detail: 'AI backend down.'}}});

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask about past projects/i), {
      target: {value: 'solar'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByText('AI backend down.')).toBeInTheDocument();
  });

  it('shows the message field when an AI search rejects without a detail', async () => {
    mockSearchPastProjectsWithAI.mockRejectedValue({response: {data: {message: 'Try later.'}}});

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask about past projects/i), {
      target: {value: 'solar'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByText('Try later.')).toBeInTheDocument();
  });

  it('shows why the API refused the query, such as a query that is too long', async () => {
    mockSearchPastProjectsWithAI.mockRejectedValue({
      response: {status: 400, data: {query: ['Query must be at most 2000 characters.']}},
    });

    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', {name: /\+ ai search table/i}));
    fireEvent.change(screen.getByPlaceholderText(/ask about past projects/i), {
      target: {value: 'x'.repeat(2100)},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByText('Query must be at most 2000 characters.')).toBeInTheDocument();
    expect(screen.queryByText(/AI search is unavailable right now/)).toBeNull();
  });
});
