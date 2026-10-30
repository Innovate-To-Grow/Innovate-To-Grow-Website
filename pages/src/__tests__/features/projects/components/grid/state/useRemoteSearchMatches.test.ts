import {act, renderHook} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  REMOTE_SEARCH_DELAY_MS,
  useRemoteSearchMatches,
  type RemoteRowSearch,
} from '@/features/projects/components/grid/state/useRemoteSearchMatches';

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return {promise, resolve, reject};
};

const renderSearch = (search: string, searchRemote?: RemoteRowSearch) =>
  renderHook(({value}) => useRemoteSearchMatches(value, searchRemote), {initialProps: {value: search}});

/** Lets the typing pause run out, then lets the answer (if any) settle. */
const pause = async (ms = REMOTE_SEARCH_DELAY_MS) => {
  await act(async () => {
    vi.advanceTimersByTime(ms);
    await Promise.resolve();
  });
};

describe('useRemoteSearchMatches', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('asks the server once typing pauses, and returns its matches for that query', async () => {
    const searchRemote = vi.fn<RemoteRowSearch>().mockResolvedValue(new Set(['p1']));
    const {result} = renderSearch('  Energy   Pro ', searchRemote);

    // Not answered yet: more rows may still match.
    expect(result.current).toEqual({matches: null, pending: true});
    await pause(REMOTE_SEARCH_DELAY_MS - 1);
    expect(searchRemote).not.toHaveBeenCalled();

    await pause(1);
    expect(searchRemote).toHaveBeenCalledTimes(1);
    expect(searchRemote.mock.calls[0][0]).toBe('Energy Pro');
    expect(result.current).toEqual({matches: new Set(['p1']), pending: false});
  });

  it('does not ask for a short query, a too long one, or without a server search', async () => {
    const searchRemote = vi.fn<RemoteRowSearch>().mockResolvedValue(new Set());
    const {result, rerender} = renderSearch('ab', searchRemote);
    await pause();
    expect(result.current).toEqual({matches: null, pending: false});

    rerender({value: 'x'.repeat(201)});
    await pause();
    expect(result.current).toEqual({matches: null, pending: false});
    expect(searchRemote).not.toHaveBeenCalled();

    const {result: withoutServer} = renderSearch('EnergyPro');
    await pause();
    expect(withoutServer.current).toEqual({matches: null, pending: false});
  });

  it('asks only for the query typing stopped at, and drops the answer to a query that changed meanwhile', async () => {
    const answers = [deferred<ReadonlySet<string>>(), deferred<ReadonlySet<string>>()];
    const searchRemote = vi.fn<RemoteRowSearch>().mockImplementation(() => answers[searchRemote.mock.calls.length - 1].promise);
    const {result, rerender} = renderSearch('Ene', searchRemote);

    // Typing on before the pause runs out: "Ene" is never asked for.
    rerender({value: 'Ener'});
    await pause();
    expect(searchRemote.mock.calls.map(([query]) => query)).toEqual(['Ener']);
    const firstSignal = searchRemote.mock.calls[0][1];

    // A new query while the first is in flight cancels it, and its late answer is not used.
    rerender({value: 'Energy'});
    expect(firstSignal.aborted).toBe(true);
    await act(async () => answers[0].resolve(new Set(['stale'])));
    expect(result.current).toEqual({matches: null, pending: true});

    await pause();
    await act(async () => answers[1].resolve(new Set(['p2'])));
    expect(result.current).toEqual({matches: new Set(['p2']), pending: false});
  });

  it('adds nothing when the server search fails', async () => {
    const searchRemote = vi.fn<RemoteRowSearch>().mockRejectedValue(new Error('Network Error'));
    const {result} = renderSearch('EnergyPro', searchRemote);

    await pause();
    expect(result.current).toEqual({matches: null, pending: false});
  });

  it('adds nothing, and stops searching, when the server declines a query too broad to narrow the list', async () => {
    const searchRemote = vi.fn<RemoteRowSearch>().mockResolvedValue(null);
    const {result} = renderSearch('the', searchRemote);

    await pause();
    expect(searchRemote).toHaveBeenCalledTimes(1);
    expect(result.current).toEqual({matches: null, pending: false});
  });

  it('cancels a pending request when the search is cleared', async () => {
    const searchRemote = vi.fn<RemoteRowSearch>().mockReturnValue(new Promise(() => {}));
    const {result, rerender} = renderSearch('EnergyPro', searchRemote);
    await pause();
    const signal = searchRemote.mock.calls[0][1];

    rerender({value: ''});
    expect(signal.aborted).toBe(true);
    expect(result.current).toEqual({matches: null, pending: false});
  });
});
