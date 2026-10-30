import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {SearchTableCard} from '@/features/projects/components/search/cards/SearchTableCard';
import {ProjectGridRowDetails} from '@/features/projects/components/grid/table/ProjectGridRowDetails';
import {
  PROJECT_DETAIL_CONCURRENCY,
  compactProjectToGridRow,
  type ProjectDetail,
  type ProjectGridRow,
} from '@/features/projects/api';
import {stubGridLayout} from '@/__tests__/features/projects/fixtures/gridLayout';

const {fetchDetail} = vi.hoisted(() => ({fetchDetail: vi.fn()}));
vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/features/projects/api')>(),
  fetchProjectDetail: fetchDetail,
}));

function compactRow(id: string): ProjectGridRow {
  return compactProjectToGridRow({
    id, semester_label: '2025-1 Spring', class_code: 'CAP', team_number: id,
    team_name: 'Team', project_title: `Project ${id}`, organization: 'Org', industry: 'Energy',
    track: null, presentation_order: null,
  });
}

function detail(id: string, fields: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    ...compactRow(id), id, track: null, presentation_order: null,
    abstract: `Abstract ${id}`, student_names: `Students ${id}`, ...fields,
  };
}

function deferredDetail() {
  let resolve!: (value: ProjectDetail) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<ProjectDetail>((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}

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

/** Shows `count` rows per page, so a page holds more rows than detail requests may run at once. */
function showRowsPerPage(count: number) {
  fireEvent.change(screen.getByLabelText('Per page'), {target: {value: String(count)}});
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
    expect(desktop().getByRole('status')).toHaveTextContent('Loading project details...');
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
    fireEvent.click(screen.getByRole('button', {name: 'Save Selected'}));
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
    fireEvent.click(mobile().getByRole('button', {name: /^Show details for /}));
    expect(await mobile().findByRole('alert')).toHaveTextContent('Unable to load project details.');
    expect(mobile().getByRole('link', {name: /open the project page/i})).toHaveAttribute('href', `${window.location.origin}/past-projects/project/retry-details`);
    expect(fetchDetail).toHaveBeenCalledTimes(1);
    fireEvent.click(mobile().getByRole('button', {name: 'Retry'}));
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

  it('skips queued work after collapsing all rows and loads it when reopened', async () => {
    const rows = Array.from({length: PROJECT_DETAIL_CONCURRENCY + 1}, (_, index) => compactRow(`collapse-details-${index}`));
    const responses = new Map(rows.map((row) => [row.id!, deferredDetail()]));
    fetchDetail.mockImplementation((id: string) => responses.get(id)!.promise);
    const {desktop} = renderTable(rows);
    showRowsPerPage(10);
    fireEvent.click(screen.getByRole('button', {name: 'View All Details'}));
    expect(fetchDetail).toHaveBeenCalledTimes(PROJECT_DETAIL_CONCURRENCY);
    const requestedIds = fetchDetail.mock.calls.map(([id]) => id as string);
    const queuedId = rows.find((row) => !requestedIds.includes(row.id!))!.id!;
    fireEvent.click(screen.getByRole('button', {name: 'Hide All Details'}));
    await act(async () => {
      requestedIds.forEach((id) => responses.get(id)!.resolve(detail(id)));
    });
    expect(fetchDetail).toHaveBeenCalledTimes(PROJECT_DETAIL_CONCURRENCY);
    fireEvent.click(screen.getByRole('button', {name: 'View All Details'}));
    expect(fetchDetail).toHaveBeenCalledTimes(rows.length);
    await act(async () => responses.get(queuedId)!.resolve(detail(queuedId)));
    expect(desktop().getByText(`Abstract ${queuedId}`)).toBeInTheDocument();
  });

  it('refreshes expired details when reopened', async () => {
    const clock = vi.spyOn(Date, 'now').mockReturnValue(1_000);
    fetchDetail.mockResolvedValueOnce(detail('expired-details', {abstract: 'Earlier abstract'}))
      .mockResolvedValueOnce(detail('expired-details', {abstract: 'Updated abstract'}));
    const {desktop} = renderTable([compactRow('expired-details')]);
    fireEvent.click(desktop().getByRole('button', {name: /^Details for /, expanded: false}));
    expect(await desktop().findByText('Earlier abstract')).toBeInTheDocument();
    fireEvent.click(desktop().getByRole('button', {name: /^Details for /, expanded: true}));
    clock.mockReturnValue(1_000 + 5 * 60 * 1_000);
    fireEvent.click(desktop().getByRole('button', {name: /^Details for /, expanded: false}));
    expect(await desktop().findByText('Updated abstract')).toBeInTheDocument();
    expect(fetchDetail).toHaveBeenCalledTimes(2);
  });

  it('copies a past project link and says so', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'clipboard', {value: {writeText}, configurable: true});
    try {
      render(<ProjectGridRowDetails row={{...compactRow('copy-me'), abstract: 'Copied abstract'}} scope="past" />);
      fireEvent.click(screen.getByRole('button', {name: /^Copy project link for /}));
      expect(await screen.findByRole('status')).toHaveTextContent('Project link copied.');
      expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/past-projects/project/copy-me`);
    } finally {
      Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
    }
  });

  it('says when a project link cannot be copied', async () => {
    render(<ProjectGridRowDetails row={{...compactRow('no-clipboard'), abstract: 'Abstract'}} scope="past" />);
    fireEvent.click(screen.getByRole('button', {name: /^Copy project link for /}));
    expect(await screen.findByRole('status')).toHaveTextContent('Could not copy the link.');
  });

  it('links current projects to their page without a copy button', () => {
    render(<ProjectGridRowDetails row={{...compactRow('current'), abstract: 'Abstract'}} scope="current" />);
    expect(screen.getByRole('link', {name: /^Open the project page for /})).toHaveAttribute('href', '/projects/current');
    expect(screen.queryByRole('button', {name: /^Copy project link/})).toBeNull();
  });
});
