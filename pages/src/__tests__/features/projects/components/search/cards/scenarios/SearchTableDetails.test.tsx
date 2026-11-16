import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {SearchTableCard} from '@/features/projects/components/search/cards/SearchTableCard';
import {ProjectGridRowDetails} from '@/features/projects/components/grid/rows/ProjectGridRowDetails';
import {PROJECT_DETAIL_CONCURRENCY, type ProjectGridRow} from '@/features/projects/api';
import {stubGridLayout} from '@/__tests__/features/projects/fixtures/gridLayout';
import {compactRow, deferredDetail, detail, showRowsPerPage} from '@/__tests__/features/projects/components/search/cards/scenarios/searchTableDetailsFixtures';

const {fetchDetail} = vi.hoisted(() => ({fetchDetail: vi.fn()}));
vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/features/projects/api')>(),
  fetchProjectDetail: fetchDetail,
}));

/** Renders a search table in the desktop layout (or the phone one); `layout.setPhone` switches between them. */
function renderTable(rows: ProjectGridRow[], onMergeSelected = vi.fn(), initialLayout: 'desktop' | 'phone' = 'desktop') {
  const layout = stubGridLayout(initialLayout);
  const view = render(
    <SearchTableCard canRemove={false} initialRows={rows} tableId="archive" title="Search Table"
      onRemove={vi.fn()} onMergeSelected={onMergeSelected} />,
  );
  return {
    ...view,
    layout,
    // Only the layout the screen shows is rendered, so each is looked up when it is used.
    desktop: () => within(view.container.querySelector('.project-grid-table-wrap') as HTMLElement),
    mobile: () => within(view.container.querySelector('.project-grid-mobile-cards') as HTMLElement),
  };
}

afterEach(() => { cleanup(); fetchDetail.mockReset(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('compact archive row details', () => {
  it('loads only on View, shares the request with mobile, and preserves selection and the individual URL', async () => {
    const response = deferredDetail();
    fetchDetail.mockReturnValue(response.promise);
    const row = compactRow('desktop-details');
    const onMerge = vi.fn();
    const {desktop, mobile, layout} = renderTable([row], onMerge);

    expect(fetchDetail).not.toHaveBeenCalled();
    fireEvent.click(desktop().getByRole('checkbox', {name: `Select ${row.project_title}`}));
    fireEvent.click(desktop().getByRole('button', {name: /^Details for /, expanded: false}));
    const detailsId = desktop().getByRole('button', {name: /^Details for /, expanded: true}).getAttribute('aria-controls');
    expect(desktop().getByRole('status')).toHaveTextContent('Loading project details…');
    expect(fetchDetail).toHaveBeenCalledExactlyOnceWith(row.id, expect.any(AbortSignal), 15_000);

    await act(async () => response.resolve(detail(row.id!)));
    expect(desktop().getByRole('button', {name: /^Details for /, expanded: true})).toHaveAttribute('aria-controls', detailsId);
    // Turned to a phone and back: the row stays open in either layout, from the same request.
    for (const isPhone of [true, false]) {
      act(() => layout.setPhone(isPhone));
      const view = isPhone ? mobile() : desktop();
      expect(view.getByText(`Abstract ${row.id}`)).toBeInTheDocument();
      expect(view.getByText(`Students ${row.id}`)).toBeInTheDocument();
      expect(view.getByRole('checkbox', {name: `Select ${row.project_title}`})).toBeChecked();
      expect(view.getByRole('link', {name: /open the project page/i})).toHaveAttribute('href', `${window.location.origin}/past-projects/project/${row.id}`);
      expect(view.getByRole('link', {name: /open the project page/i})).toHaveAttribute('target', '_blank');
    }
    expect(fetchDetail).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', {name: 'Add to Curation'}));
    expect(onMerge).toHaveBeenCalledWith([row], expect.objectContaining({reportProgress: expect.any(Function)}));
    // The detail cache enriches presentation only; row identity and merge inputs stay stable.
    expect(row.abstract).toBe('');
    fireEvent.click(desktop().getByRole('button', {name: /^Details for /, expanded: true}));
    fireEvent.click(desktop().getByRole('button', {name: /^Details for /, expanded: false}));
    expect(desktop().getByText(`Abstract ${row.id}`)).toBeInTheDocument();
    expect(fetchDetail).toHaveBeenCalledTimes(1);
  });

  it('shows a failure without losing the link and retries from mobile in both layouts', async () => {
    fetchDetail.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(detail('retry-details'));
    const {desktop, mobile, layout} = renderTable([compactRow('retry-details')], vi.fn(), 'phone');
    fireEvent.click(mobile().getByRole('button', {name: /^Show Details for /}));
    expect(await mobile().findByRole('alert')).toHaveTextContent('Unable to load project details.');
    expect(mobile().getByRole('link', {name: /open the project page/i})).toHaveAttribute('href', `${window.location.origin}/past-projects/project/retry-details`);
    expect(fetchDetail).toHaveBeenCalledTimes(1);
    // An outline Try Again, named after its row.
    const tryAgain = mobile().getByRole('button', {name: 'Try Again for Project retry-details'});
    expect(tryAgain).toHaveClass('itg-btn', 'itg-btn-outline');
    fireEvent.click(tryAgain);
    await waitFor(() => expect(mobile().getByText('Students retry-details')).toBeInTheDocument());
    act(() => layout.setPhone(false));
    expect(desktop().getByText('Abstract retry-details')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(fetchDetail).toHaveBeenCalledTimes(2);
  });

  it('remembers a successful empty detail response across collapse and reopening', async () => {
    fetchDetail.mockResolvedValue(detail('empty-details', {abstract: '', student_names: ''}));
    const {desktop} = renderTable([compactRow('empty-details')]);
    fireEvent.click(desktop().getByRole('button', {name: /^Details for /, expanded: false}));
    expect(await desktop().findByText('No abstract or student names available.')).toBeInTheDocument();
    fireEvent.click(desktop().getByRole('button', {name: /^Details for /, expanded: true}));
    fireEvent.click(desktop().getByRole('button', {name: /^Details for /, expanded: false}));
    expect(desktop().getByText('No abstract or student names available.')).toBeInTheDocument();
    expect(fetchDetail).toHaveBeenCalledTimes(1);
  });

  it('limits View All Details requests and loads each project once across both layouts', async () => {
    const rows = Array.from({length: PROJECT_DETAIL_CONCURRENCY + 1}, (_, index) => compactRow(`all-details-${index}`));
    const responses = new Map(rows.map((row) => [row.id!, deferredDetail()]));
    fetchDetail.mockImplementation((id: string) => responses.get(id)!.promise);
    const {desktop, mobile, layout} = renderTable(rows);
    showRowsPerPage(10);
    fireEvent.click(screen.getByRole('button', {name: 'View All Details'}));
    expect(fetchDetail).toHaveBeenCalledTimes(PROJECT_DETAIL_CONCURRENCY);
    const firstId = fetchDetail.mock.calls[0][0] as string;
    await act(async () => responses.get(firstId)!.resolve(detail(firstId)));
    expect(fetchDetail).toHaveBeenCalledTimes(rows.length);
    await act(async () => {
      rows.forEach((row) => responses.get(row.id!)!.resolve(detail(row.id!)));
    });
    for (const row of rows) expect(desktop().getByText(`Abstract ${row.id}`)).toBeInTheDocument();
    act(() => layout.setPhone(true));
    for (const row of rows) expect(mobile().getByText(`Students ${row.id}`)).toBeInTheDocument();
    act(() => layout.setPhone(false));
    fireEvent.click(screen.getByRole('button', {name: 'Hide All Details'}));
    fireEvent.click(screen.getByRole('button', {name: 'View All Details'}));
    expect(fetchDetail).toHaveBeenCalledTimes(rows.length);
  });

  it('preserves saved snapshot fields and does not request details for existing content', () => {
    const snapshot = compactRow('saved-snapshot');
    const {rerender} = render(<ProjectGridRowDetails row={snapshot} scope="past" />);
    expect(fetchDetail).not.toHaveBeenCalled();
    rerender(<ProjectGridRowDetails row={{...snapshot, abstract: 'Saved abstract'}} scope="past" loadMissingDetails />);
    expect(screen.getByText('Saved abstract')).toBeInTheDocument();
    expect(fetchDetail).not.toHaveBeenCalled();
  });
});
