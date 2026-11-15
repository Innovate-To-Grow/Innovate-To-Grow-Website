import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {SharedPastProjectMergeSearch} from '@/features/projects/components/shared/search/SharedPastProjectMergeSearch';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {alphaRow, bravoRow, charlieRow} from '@/__tests__/features/projects/components/shared/search/sharedPastProjectMergeSearchFixtures';

const mockUseAuth = vi.fn();
const mockSearchPastProjectsWithAI = vi.fn();
const mockHydrateProjectGridRowsSettled = vi.fn();
const mockBuildLoginPath = vi.fn();

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

describe('SharedPastProjectMergeSearch — AI search table', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue({isAuthenticated: true});
    mockSearchPastProjectsWithAI.mockReset();
    mockHydrateProjectGridRowsSettled.mockReset();
    mockHydrateProjectGridRowsSettled.mockImplementation(async (rows: ProjectGridRow[]) => ({
      rows,
      failedIndexes: [],
      unavailableIndexes: [],
    }));
    mockBuildLoginPath.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows an unavailable message when AI search is not configured', async () => {
    mockSearchPastProjectsWithAI.mockResolvedValue({
      available: false,
      message: 'Not configured.',
      query: 'solar',
      results: [],
      usage: {},
    });

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
    fireEvent.change(screen.getByPlaceholderText(/ask about past projects/i), {
      target: {value: 'solar'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByText(/AI search is not available on this site right now/)).toBeInTheDocument();
    expect(screen.queryByText('Not configured.')).toBeNull();
  });

  it('shows a no-results message when AI search finds nothing', async () => {
    mockSearchPastProjectsWithAI.mockResolvedValue({
      available: true,
      query: 'solar',
      results: [],
      usage: {},
    });

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
    fireEvent.change(screen.getByPlaceholderText(/ask about past projects/i), {
      target: {value: 'solar'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByText('AI search did not find matching past projects.')).toBeInTheDocument();
  });

  it('navigates to login when the sign-in dialog is confirmed', () => {
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

    fireEvent.click(screen.getByRole('button', {name: 'AI Search Table'}));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: /sign in/i}));

    expect(mockBuildLoginPath).toHaveBeenCalled();
  });
});
