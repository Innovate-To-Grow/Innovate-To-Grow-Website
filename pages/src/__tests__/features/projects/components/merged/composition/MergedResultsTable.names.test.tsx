import {cleanup, render, screen, within} from '@testing-library/react';
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

const items = () => createProjectGridItems([makeRow('T01', 'Alpha Project'), makeRow('T02', 'Bravo Project')], 'names');

const desktopRemoveNames = () =>
  within(document.querySelector('.project-grid-table-wrap') as HTMLElement)
    .getAllByRole('button', {name: /^Remove /})
    .map((button) => button.getAttribute('aria-label') ?? button.textContent);

describe('MergedResultsTable — row Remove buttons name their project', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({isAuthenticated: true, isInitializing: false, unverified: false, user: null});
  });

  afterEach(() => {
    cleanup();
  });

  it('in the curation draft', () => {
    render(<MergedResultsTable rows={items()} onDeleteRow={vi.fn()} onCreateShare={vi.fn()} />);

    expect(desktopRemoveNames()).toEqual(['Remove Alpha Project', 'Remove Bravo Project']);
    // The visible word leads the name, for speech input.
    screen.getAllByRole('button', {name: 'Remove Alpha Project'}).forEach((button) => expect(button).toHaveTextContent('Remove'));
  });

  it("on the owner's curation page", () => {
    render(<MergedResultsTable rows={items()} sharedMode editable title="Owner curation" onUpdateShare={vi.fn()} />);

    expect(desktopRemoveNames()).toEqual(['Remove Alpha Project', 'Remove Bravo Project']);
  });
});
