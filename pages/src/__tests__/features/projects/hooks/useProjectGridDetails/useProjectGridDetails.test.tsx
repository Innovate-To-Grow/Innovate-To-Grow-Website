import {cleanup, render, screen, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {useProjectGridDetails} from '@/features/projects/hooks/useProjectGridDetails';
import {
  PROJECT_DETAIL_CONCURRENCY,
  readCachedProjectDetail,
  type ProjectDetail,
  type ProjectGridRow,
} from '@/features/projects/api';

const {mockFetchProjectDetail} = vi.hoisted(() => ({mockFetchProjectDetail: vi.fn()}));

vi.mock('@/features/projects/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/projects/api')>()),
  fetchProjectDetail: (...args: unknown[]) => mockFetchProjectDetail(...args),
}));

const compactRow = (id: string): ProjectGridRow => ({
  id,
  semester_label: '2025 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'Team',
  project_title: `Project ${id}`,
  organization: 'Org',
  industry: 'Energy',
  abstract: '',
  student_names: '',
  is_presenting: '',
});

const detail = (id: string): ProjectDetail => ({
  id,
  project_title: `Project ${id}`,
  team_name: 'Team',
  team_number: '101',
  organization: 'Org',
  industry: 'Energy',
  abstract: `Abstract of ${id}`,
  student_names: 'Ada Lovelace',
  class_code: 'CAP',
  track: null,
  presentation_order: null,
  semester_label: '2025-1 Spring',
});

/** A request that never answers (a stalled connection); it fails only when aborted. */
const stalledRequest = (_id: string, signal: AbortSignal) =>
  new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(Object.assign(new Error('canceled'), {code: 'ERR_CANCELED'})));
  });

const RowDetails = ({id}: {id: string}) => {
  const {loading, error, details} = useProjectGridDetails(compactRow(id), true);
  return <p data-testid={id}>{loading ? 'loading' : error ? 'error' : details.abstract}</p>;
};

const Rows = ({ids}: {ids: string[]}) => (
  <>
    {ids.map((id) => (
      <RowDetails key={id} id={id} />
    ))}
  </>
);

const idsFor = (prefix: string, count: number) => Array.from({length: count}, (_, index) => `${prefix}-${index + 1}`);

describe('useProjectGridDetails', () => {
  afterEach(() => {
    cleanup();
    mockFetchProjectDetail.mockReset();
  });

  it('gives each details request a timeout, so a stalled one cannot hold its slot for good', async () => {
    mockFetchProjectDetail.mockResolvedValue(detail('timeout-1'));

    render(<Rows ids={['timeout-1']} />);

    expect(await screen.findByText('Abstract of timeout-1')).toBeInTheDocument();
    expect(mockFetchProjectDetail).toHaveBeenCalledWith('timeout-1', expect.any(AbortSignal), 15_000);
  });

  it('drops the requests of rows that were closed, so the rows opened after them load', async () => {
    mockFetchProjectDetail.mockImplementation(stalledRequest);
    const stalled = idsFor('stalled', PROJECT_DETAIL_CONCURRENCY);

    const view = render(<Rows ids={stalled} />);
    await waitFor(() => expect(mockFetchProjectDetail).toHaveBeenCalledTimes(PROJECT_DETAIL_CONCURRENCY));

    // Every slot is taken: one more row waits in the queue.
    view.rerender(<Rows ids={[...stalled, 'waiting']} />);
    expect(screen.getByTestId('waiting')).toHaveTextContent('loading');
    expect(mockFetchProjectDetail).toHaveBeenCalledTimes(PROJECT_DETAIL_CONCURRENCY);

    // The stalled rows are closed: their requests are dropped and the waiting row's request is sent.
    mockFetchProjectDetail.mockImplementation(async (id: string) => detail(id));
    view.rerender(<Rows ids={['waiting']} />);

    expect(await screen.findByText('Abstract of waiting')).toBeInTheDocument();
    const stalledSignals = mockFetchProjectDetail.mock.calls
      .slice(0, PROJECT_DETAIL_CONCURRENCY)
      .map(([, signal]) => signal as AbortSignal);
    expect(stalledSignals.every((signal) => signal.aborted)).toBe(true);
  });

  it('loads a dropped row again when it is opened again', async () => {
    mockFetchProjectDetail.mockImplementation(stalledRequest);

    const view = render(<Rows ids={['reopened']} />);
    await waitFor(() => expect(mockFetchProjectDetail).toHaveBeenCalledTimes(1));
    view.rerender(<Rows ids={[]} />);
    await waitFor(() => expect((mockFetchProjectDetail.mock.calls[0][1] as AbortSignal).aborted).toBe(true));

    mockFetchProjectDetail.mockImplementation(async (id: string) => detail(id));
    view.rerender(<Rows ids={['reopened']} />);

    expect(await screen.findByText('Abstract of reopened')).toBeInTheDocument();
    expect(mockFetchProjectDetail).toHaveBeenCalledTimes(2);
  });

  it('keeps the request of a row that is still shown elsewhere', async () => {
    let answer!: (value: ProjectDetail) => void;
    mockFetchProjectDetail.mockReturnValue(new Promise((resolve) => (answer = resolve)));

    // The same project in two tables: closing it in one leaves the other waiting for the same request.
    const view = render(
      <>
        <Rows ids={['shared']} />
        <div data-testid="second-table">
          <RowDetails id="shared" />
        </div>
      </>,
    );
    await waitFor(() => expect(mockFetchProjectDetail).toHaveBeenCalledTimes(1));
    view.rerender(
      <div data-testid="second-table">
        <RowDetails id="shared" />
      </div>,
    );
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect((mockFetchProjectDetail.mock.calls[0][1] as AbortSignal).aborted).toBe(false);
    answer(detail('shared'));
    expect(await screen.findByText('Abstract of shared')).toBeInTheDocument();
  });

  it('shows an error, not a dropped request, when the request itself fails', async () => {
    mockFetchProjectDetail.mockRejectedValue(Object.assign(new Error('timeout of 15000ms exceeded'), {code: 'ECONNABORTED'}));

    render(<Rows ids={['failing']} />);

    expect(await screen.findByText('error')).toBeInTheDocument();
  });

  it('loads the abstract of an archive row that arrived with its student names', async () => {
    mockFetchProjectDetail.mockImplementation(async (id: string) => detail(id));
    const WithNames = () => {
      const {loading, details} = useProjectGridDetails({...compactRow('with-names'), student_names: 'Ada Lovelace'}, true);
      return <p>{loading ? 'loading' : details.abstract}</p>;
    };

    render(<WithNames />);

    expect(await screen.findByText('Abstract of with-names')).toBeInTheDocument();
    expect(mockFetchProjectDetail).toHaveBeenCalledWith('with-names', expect.any(AbortSignal), 15_000);
  });

  it('keeps loaded details for a save of the same rows', async () => {
    mockFetchProjectDetail.mockImplementation(async (id: string) => detail(id));

    render(<Rows ids={['remembered']} />);

    expect(await screen.findByText('Abstract of remembered')).toBeInTheDocument();
    expect(readCachedProjectDetail('remembered')).toMatchObject({abstract: 'Abstract of remembered'});
  });
});
