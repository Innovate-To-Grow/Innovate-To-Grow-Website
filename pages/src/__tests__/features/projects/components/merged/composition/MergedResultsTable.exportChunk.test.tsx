import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '@/features/projects/components/merged/composition/MergedResultsTable';
import {createProjectGridItems, type ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

const mockUseAuth = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {...actual, useAuth: () => mockUseAuth()};
});

// The PDF exporter's own chunk cannot be loaded, as in a tab opened before a deploy removed it.
vi.mock('@/features/projects/components/export/formats/pdfExport', () => {
  throw new TypeError('Importing a module script failed.');
});

const row: ProjectGridRow = {
  semester_label: '2025-1 Spring',
  class_code: 'ENGR 120',
  team_number: 'T01',
  team_name: 'Team Alpha',
  project_title: 'Shared Project',
  organization: 'Acme',
  industry: 'Technology',
  abstract: 'A detailed project abstract.',
  student_names: 'Alice, Bob',
  is_presenting: '',
};

describe('MergedResultsTable — an export whose code is missing', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({isAuthenticated: false, user: null});
  });

  afterEach(() => {
    cleanup();
  });

  it('asks a curation page viewer to reload the page instead of trying again', async () => {
    const {container} = render(
      <MergedResultsTable rows={createProjectGridItems([row], 'test')} sharedMode title="Water picks" />,
    );
    const exportCluster = container.querySelector('.project-grid-toolbar-cluster[aria-label="Export"]') as HTMLElement;

    fireEvent.click(within(exportCluster).getByRole('button', {name: 'PDF'}));

    expect(
      await screen.findByText(
        'Unable to export PDF: part of this page did not download, often because the site was updated. ' +
          'Reload the page, then export again.',
      ),
    ).toBeInTheDocument();
    expect(within(exportCluster).getByRole('button', {name: 'Reload Page'})).toBeInTheDocument();
    // The other formats still export, and are not blocked by the failed one.
    expect(within(exportCluster).getByRole('button', {name: 'Excel'})).not.toHaveAttribute('aria-disabled');
  });
});
