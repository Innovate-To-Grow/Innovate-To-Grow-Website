import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {SearchTableCard} from '@/features/projects/components/SearchTableCard';
import {ProjectGridRowDetails} from '@/features/projects/components/grid/ProjectGridRowDetails';
import {compactProjectToGridRow, type ProjectDetail, type ProjectGridRow} from '@/features/projects/api';

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

function renderTable(rows: ProjectGridRow[], onMergeSelected = vi.fn()) {
  const view = render(
    <SearchTableCard canRemove={false} initialRows={rows} tableId="archive" title="Search Table"
      onRemove={vi.fn()} onMergeSelected={onMergeSelected} />,
  );
  return {
    ...view,
    desktop: within(view.container.querySelector('.project-grid-table-wrap') as HTMLElement),
    mobile: within(view.container.querySelector('.project-grid-mobile-cards') as HTMLElement),
  };
}

afterEach(() => { cleanup(); fetchDetail.mockReset(); vi.restoreAllMocks(); });

describe('compact archive row details', () => {
  it('loads only on View, shares the request with mobile, and preserves selection and the individual URL', async () => {
    const response = deferredDetail();
    fetchDetail.mockReturnValue(response.promise);
    const row = compactRow('desktop-details');
    const onMerge = vi.fn();
    const {desktop, mobile} = renderTable([row], onMerge);

    expect(fetchDetail).not.toHaveBeenCalled();
    fireEvent.click(desktop.getByRole('checkbox', {name: `Select ${row.project_title}`}));
    fireEvent.click(desktop.getByRole('button', {name: 'View'}));
    const detailsId = desktop.getByRole('button', {name: 'Hide'}).getAttribute('aria-controls');
    expect(desktop.getByRole('status')).toHaveTextContent('Loading project details...');
    expect(mobile.getByRole('status')).toHaveTextContent('Loading project details...');
    expect(fetchDetail).toHaveBeenCalledExactlyOnceWith(row.id);

    await act(async () => response.resolve(detail(row.id!)));
    for (const layout of [desktop, mobile]) {
      expect(layout.getByText(`Abstract ${row.id}`)).toBeInTheDocument();
      expect(layout.getByText(`Students ${row.id}`)).toBeInTheDocument();
      expect(layout.getByRole('checkbox', {name: `Select ${row.project_title}`})).toBeChecked();
      expect(layout.getByRole('link')).toHaveAttribute('href', `${window.location.origin}/past-projects/project/${row.id}`);
      expect(layout.getByRole('link')).toHaveAttribute('target', '_blank');
    }
    expect(desktop.getByRole('button', {name: 'Hide'})).toHaveAttribute('aria-controls', detailsId);
    fireEvent.click(screen.getByRole('button', {name: 'Save Selected'}));
    expect(onMerge).toHaveBeenCalledWith([row]);
    // The detail cache enriches presentation only; row identity and merge inputs stay stable.
    expect(row.abstract).toBe('');
    fireEvent.click(desktop.getByRole('button', {name: 'Hide'}));
    fireEvent.click(desktop.getByRole('button', {name: 'View'}));
    expect(desktop.getByText(`Abstract ${row.id}`)).toBeInTheDocument();
    expect(fetchDetail).toHaveBeenCalledTimes(1);
  });

  it('shows a failure without losing the link and retries from mobile in both layouts', async () => {
    fetchDetail.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(detail('retry-details'));
    const {desktop, mobile} = renderTable([compactRow('retry-details')]);
    fireEvent.click(mobile.getByRole('button', {name: 'View Details'}));
    expect(await mobile.findByRole('alert')).toHaveTextContent('Unable to load project details.');
    expect(mobile.getByRole('link')).toHaveAttribute('href', `${window.location.origin}/past-projects/project/retry-details`);
    expect(fetchDetail).toHaveBeenCalledTimes(1);
    fireEvent.click(mobile.getByRole('button', {name: 'Retry'}));
    await waitFor(() => expect(desktop.getByText('Abstract retry-details')).toBeInTheDocument());
    expect(mobile.getByText('Students retry-details')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(fetchDetail).toHaveBeenCalledTimes(2);
  });

  it('remembers a successful empty detail response across collapse and reopening', async () => {
    fetchDetail.mockResolvedValue(detail('empty-details', {abstract: '', student_names: ''}));
    const {desktop} = renderTable([compactRow('empty-details')]);
    fireEvent.click(desktop.getByRole('button', {name: 'View'}));
    expect(await desktop.findByText('No abstract or student names available.')).toBeInTheDocument();
    fireEvent.click(desktop.getByRole('button', {name: 'Hide'}));
    fireEvent.click(desktop.getByRole('button', {name: 'View'}));
    expect(desktop.getByText('No abstract or student names available.')).toBeInTheDocument();
    expect(fetchDetail).toHaveBeenCalledTimes(1);
  });

  it('limits View All Details requests and loads each project once across both layouts', async () => {
    const rows = Array.from({length: 5}, (_, index) => compactRow(`all-details-${index}`));
    const responses = new Map(rows.map((row) => [row.id!, deferredDetail()]));
    fetchDetail.mockImplementation((id: string) => responses.get(id)!.promise);
    const {desktop, mobile} = renderTable(rows);
    fireEvent.click(screen.getByRole('button', {name: 'View All Details'}));
    expect(fetchDetail).toHaveBeenCalledTimes(4);
    const firstId = fetchDetail.mock.calls[0][0] as string;
    await act(async () => responses.get(firstId)!.resolve(detail(firstId)));
    expect(fetchDetail).toHaveBeenCalledTimes(5);
    await act(async () => {
      rows.forEach((row) => responses.get(row.id!)!.resolve(detail(row.id!)));
    });
    for (const row of rows) {
      expect(desktop.getByText(`Abstract ${row.id}`)).toBeInTheDocument();
      expect(mobile.getByText(`Students ${row.id}`)).toBeInTheDocument();
    }
    fireEvent.click(screen.getByRole('button', {name: 'Hide All Details'}));
    fireEvent.click(screen.getByRole('button', {name: 'View All Details'}));
    expect(fetchDetail).toHaveBeenCalledTimes(5);
  });

  it('preserves saved snapshot fields and does not request details for existing content', () => {
    const snapshot = compactRow('saved-snapshot');
    const {rerender} = render(<ProjectGridRowDetails row={snapshot} />);
    expect(fetchDetail).not.toHaveBeenCalled();
    rerender(<ProjectGridRowDetails row={{...snapshot, abstract: 'Saved abstract'}} loadMissingDetails />);
    expect(screen.getByText('Saved abstract')).toBeInTheDocument();
    expect(fetchDetail).not.toHaveBeenCalled();
  });

  it('skips queued work after collapsing all rows and loads it when reopened', async () => {
    const rows = Array.from({length: 5}, (_, index) => compactRow(`collapse-details-${index}`));
    const responses = new Map(rows.map((row) => [row.id!, deferredDetail()]));
    fetchDetail.mockImplementation((id: string) => responses.get(id)!.promise);
    const {desktop} = renderTable(rows);
    fireEvent.click(screen.getByRole('button', {name: 'View All Details'}));
    expect(fetchDetail).toHaveBeenCalledTimes(4);
    const requestedIds = fetchDetail.mock.calls.map(([id]) => id as string);
    const queuedId = rows.find((row) => !requestedIds.includes(row.id!))!.id!;
    fireEvent.click(screen.getByRole('button', {name: 'Hide All Details'}));
    await act(async () => {
      requestedIds.forEach((id) => responses.get(id)!.resolve(detail(id)));
    });
    expect(fetchDetail).toHaveBeenCalledTimes(4);
    fireEvent.click(screen.getByRole('button', {name: 'View All Details'}));
    expect(fetchDetail).toHaveBeenCalledTimes(5);
    await act(async () => responses.get(queuedId)!.resolve(detail(queuedId)));
    expect(desktop.getByText(`Abstract ${queuedId}`)).toBeInTheDocument();
  });

  it('refreshes expired details when reopened', async () => {
    const clock = vi.spyOn(Date, 'now').mockReturnValue(1_000);
    fetchDetail.mockResolvedValueOnce(detail('expired-details', {abstract: 'Earlier abstract'}))
      .mockResolvedValueOnce(detail('expired-details', {abstract: 'Updated abstract'}));
    const {desktop} = renderTable([compactRow('expired-details')]);
    fireEvent.click(desktop.getByRole('button', {name: 'View'}));
    expect(await desktop.findByText('Earlier abstract')).toBeInTheDocument();
    fireEvent.click(desktop.getByRole('button', {name: 'Hide'}));
    clock.mockReturnValue(1_000 + 5 * 60 * 1_000);
    fireEvent.click(desktop.getByRole('button', {name: 'View'}));
    expect(await desktop.findByText('Updated abstract')).toBeInTheDocument();
    expect(fetchDetail).toHaveBeenCalledTimes(2);
  });
});
