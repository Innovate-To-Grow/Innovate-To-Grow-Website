import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {SharedPastProjectMergeSearch} from '@/features/projects/components/shared/search/SharedPastProjectMergeSearch';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import type {ProjectTableRow} from '@/features/projects/api';
import {alphaRow, bravoRow, charlieRow, makeRow} from '@/__tests__/features/projects/components/shared/search/sharedPastProjectMergeSearchFixtures';

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

    fireEvent.change(screen.getByPlaceholderText(/ask about past projects/i), {
      target: {value: 'solar pump'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Search'}));

    expect(await screen.findByRole('heading', {level: 3, name: 'AI Search Table: solar pump'})).toBeInTheDocument();
    expect(mockSearchPastProjectsWithAI).toHaveBeenCalledWith('solar pump', 10, 'past');

    const aiTable = screen
      .getByRole('heading', {level: 3, name: 'AI Search Table: solar pump'})
      .closest('section') as HTMLElement;
    fireEvent.click((await within(aiTable).findAllByLabelText('Select Solar Pump Station'))[0]);
    await waitFor(() => expect(within(aiTable).getByRole('button', {name: 'Add to Curation'})).toBeEnabled());
    fireEvent.click(within(aiTable).getByRole('button', {name: 'Add to Curation'}));

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
    fireEvent.change(screen.getByPlaceholderText(/ask about past projects/i), {
      target: {value: 'solar pump'},
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
    expect(document.querySelector('.past-projects-ai-search-spinner')).toBeNull();
    expect(document.querySelector('.past-projects-ai-search-progress')).toBeNull();
    expect(screen.getByText('Searching past projects with AI…').closest('.project-grid-controls-status')).toBeNull();

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
});
