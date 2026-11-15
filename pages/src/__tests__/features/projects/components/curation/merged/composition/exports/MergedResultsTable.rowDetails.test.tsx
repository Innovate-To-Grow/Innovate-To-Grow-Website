
import {act, cleanup, fireEvent, render, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '@/features/projects/components/curation/merged/composition/MergedResultsTable';
import {createProjectGridItems, type ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {stubGridLayout} from '@/__tests__/features/projects/fixtures/gridLayout';

const mockUseAuth = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

// The export functions are heavy (dynamic imports of exceljs/jspdf + downloads) and are covered
// directly in the export module tests; here we stub them so we can assert the component's wiring
// and error handling without triggering real downloads.
const exportMocks = vi.hoisted(() => ({
  exportProjectRowsExcel: vi.fn(),
  exportProjectRowsPdf: vi.fn(),
  exportProjectRowsWord: vi.fn(),
}));

vi.mock('@/features/projects/components/export/formats/excelExport', () => ({
  exportProjectRowsExcel: exportMocks.exportProjectRowsExcel,
}));
vi.mock('@/features/projects/components/export/formats/pdfExport', () => ({
  exportProjectRowsPdf: exportMocks.exportProjectRowsPdf,
}));
vi.mock('@/features/projects/components/export/formats/wordExport', () => ({
  exportProjectRowsWord: exportMocks.exportProjectRowsWord,
}));

const baseRow: ProjectGridRow = {
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

const rowWithId: ProjectGridRow = {
  ...baseRow,
  id: '11111111-1111-4111-8111-111111111111',
};

const makeItems = (rows: ProjectGridRow[] = [baseRow]) => createProjectGridItems(rows, 'test');

// Desktop and mobile tables both render, so per-row content appears twice. Scope queries to the
// desktop table to get a single match.
const desktopTable = (container: HTMLElement) =>
  container.querySelector('.project-grid-table-wrap') as HTMLElement;

describe('MergedResultsTable exports and row details', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue({isAuthenticated: true});
    exportMocks.exportProjectRowsExcel.mockReset().mockResolvedValue(undefined);
    exportMocks.exportProjectRowsPdf.mockReset().mockResolvedValue(undefined);
    exportMocks.exportProjectRowsWord.mockReset().mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('links to the project page from expanded desktop and mobile details', () => {
    const layout = stubGridLayout('desktop');
    const {container} = render(<MergedResultsTable rows={makeItems([rowWithId])} />);

    const desktopDetailsButton = within(desktopTable(container)).getByRole('button', {name: /^Details for /});
    expect(desktopDetailsButton).toHaveAttribute('aria-expanded', 'false');
    const desktopDetailsId = desktopDetailsButton.getAttribute('aria-controls');
    expect(desktopDetailsId).toBeTruthy();

    fireEvent.click(desktopDetailsButton);
    expect(desktopDetailsButton).toHaveAttribute('aria-expanded', 'true');
    expect(document.getElementById(desktopDetailsId as string)).not.toBeNull();

    const expectedHref = new URL(`/past-projects/project/${rowWithId.id}`, window.location.origin).href;
    const desktopLink = desktopTable(container).querySelector('.project-grid-individual-link') as HTMLAnchorElement;
    expect(desktopLink).not.toBeNull();
    expect(desktopLink.getAttribute('href')).toBe(expectedHref);
    expect(desktopLink).toHaveTextContent('Open the Project Page');
    expect(desktopLink).toHaveAttribute('target', '_blank');
    expect(within(desktopTable(container)).getByRole('button', {name: /^Copy Project Link for /})).toBeVisible();

    // On a phone the same row is open in the list.
    act(() => layout.setPhone(true));
    const mobileCards = container.querySelector('.project-grid-mobile-cards') as HTMLElement;
    const mobileLink = mobileCards.querySelector('.project-grid-individual-link') as HTMLAnchorElement;
    expect(mobileLink).not.toBeNull();
    expect(mobileLink.getAttribute('href')).toBe(expectedHref);
    expect(mobileLink).toHaveTextContent('Open the Project Page');
    const mobileDetailsButton = within(mobileCards).getByRole('button', {name: /^Hide Details for /});
    expect(mobileDetailsButton).toHaveAttribute('aria-expanded', 'true');
    const mobileDetailsId = mobileDetailsButton.getAttribute('aria-controls');
    expect(mobileDetailsId).toBeTruthy();
    expect(document.getElementById(mobileDetailsId as string)).not.toBeNull();
    vi.unstubAllGlobals();
  });

  it('exposes the current desktop sort direction to assistive technology', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} />);
    const table = desktopTable(container);
    const semesterHeader = within(table).getByRole('columnheader', {name: 'Term'});
    const titleHeader = within(table).getByRole('columnheader', {name: 'Project'});

    expect(semesterHeader).toHaveAttribute('aria-sort', 'descending');
    expect(titleHeader).toHaveAttribute('aria-sort', 'none');

    fireEvent.click(within(titleHeader).getByRole('button'));

    expect(semesterHeader).toHaveAttribute('aria-sort', 'none');
    expect(titleHeader).toHaveAttribute('aria-sort', 'ascending');
  });

  it('lets an id-only row expand so its individual project URL is reachable', () => {
    const idOnlyRow: ProjectGridRow = {...rowWithId, abstract: '', student_names: ''};
    const {container} = render(<MergedResultsTable rows={makeItems([idOnlyRow])} />);
    const detailButton = within(desktopTable(container)).getByRole('button', {name: /^Details for /});

    expect(detailButton).toBeEnabled();
    fireEvent.click(detailButton);

    const expectedHref = new URL(`/past-projects/project/${rowWithId.id}`, window.location.origin).href;
    const desktopLink = desktopTable(container).querySelector('.project-grid-individual-link') as HTMLAnchorElement;
    expect(desktopLink).not.toBeNull();
    expect(desktopLink.getAttribute('href')).toBe(expectedHref);
    expect(desktopLink).toHaveTextContent('Open the Project Page');
  });

  it('does not show an individual link for legacy rows without an id', () => {
    const {container} = render(<MergedResultsTable rows={makeItems()} />);

    fireEvent.click(within(desktopTable(container)).getByRole('button', {name: /^Details for /}));

    expect(desktopTable(container).querySelector('.project-grid-individual-link')).toBeNull();
    expect(within(desktopTable(container)).queryByRole('link')).toBeNull();
  });
});
