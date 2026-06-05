import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from './PastProjectsBuilder';
import type {ProjectGridRow} from './projectGrid';

const mockUseAuth = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
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

const ROWS: ProjectGridRow[] = [
  makeRow({team_number: 'T01', team_name: 'Team Alpha', project_title: 'Alpha Project'}),
  makeRow({team_number: 'T02', team_name: 'Team Bravo', project_title: 'Bravo Project'}),
  makeRow({team_number: 'T03', team_name: 'Team Charlie', project_title: 'Charlie Project'}),
];

const getMergedSection = () => {
  const heading = screen.queryByRole('heading', {name: /saved merged results/i});
  return heading ? (heading.closest('section') as HTMLElement) : null;
};

describe('PastProjectsBuilder — Save/Merge selection contract', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue({isAuthenticated: true});
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('merges ONLY the checked rows, not the whole table', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    // No saved results yet.
    expect(getMergedSection()).toBeNull();

    // Check exactly one row, then Save/Merge. (The grid renders a desktop table
    // and mobile cards, so each row's checkbox/label appears twice — target the
    // first match; both checkboxes map to the same row key.)
    fireEvent.click(screen.getAllByLabelText('Select Bravo Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /save\/merge results/i}));

    const merged = getMergedSection();
    expect(merged).not.toBeNull();
    const mergedView = within(merged as HTMLElement);
    // Only the selected project is saved.
    expect(mergedView.getAllByText('Bravo Project').length).toBeGreaterThan(0);
    expect(mergedView.queryByText('Alpha Project')).toBeNull();
    expect(mergedView.queryByText('Charlie Project')).toBeNull();
  });

  it('disables Save/Merge until a row is selected and never merges everything by default', () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    const mergeButton = screen.getByRole('button', {name: /save\/merge results/i});
    expect(mergeButton).toBeDisabled();

    // Selecting a row enables it.
    fireEvent.click(screen.getAllByLabelText('Select Alpha Project')[0]);
    expect(mergeButton).toBeEnabled();
  });
});
