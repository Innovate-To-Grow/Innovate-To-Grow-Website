import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
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
      fireEvent.click(screen.getByRole('button', {name: /^Copy Project Link for /}));
      expect(await screen.findByRole('status')).toHaveTextContent('Project link copied.');
      expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/past-projects/project/copy-me`);
    } finally {
      Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
    }
  });

  it('says when a project link cannot be copied', async () => {
    render(<ProjectGridRowDetails row={{...compactRow('no-clipboard'), abstract: 'Abstract'}} scope="past" />);
    fireEvent.click(screen.getByRole('button', {name: /^Copy Project Link for /}));
    expect(await screen.findByRole('status')).toHaveTextContent('Could not copy the link.');
  });

  it('links current projects to their page without a copy button', () => {
    render(<ProjectGridRowDetails row={{...compactRow('current'), abstract: 'Abstract'}} scope="current" />);
    expect(screen.getByRole('link', {name: /^Open the Project Page for /})).toHaveAttribute('href', '/projects/current');
    expect(screen.queryByRole('button', {name: /^Copy Project Link/})).toBeNull();
  });
});
