import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {SharedPastProjectMergeSearch} from '@/features/projects/components/shared/search/SharedPastProjectMergeSearch';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import type {ProjectTableRow} from '@/features/projects/api';
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
    fireEvent.change(screen.getByPlaceholderText(/ask about past projects/i), {
      target: {value: 'alpha'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByText('AI found projects that are already in this curation.')).toBeInTheDocument();
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

    const addAIButton = screen.getByRole('button', {name: 'AI Search Table'});
    expect(addAIButton).toBeEnabled();
    expect(addAIButton).not.toHaveAttribute('aria-disabled');
    expect(addAIButton).toHaveClass('is-login-required');

    fireEvent.click(addAIButton);

    expect(screen.getByRole('dialog', {name: /sign in required/i})).toBeInTheDocument();
    expect(screen.getByText('You need to sign in before using AI search.')).toBeInTheDocument();
    expect(mockSearchPastProjectsWithAI).not.toHaveBeenCalled();
  });
});
