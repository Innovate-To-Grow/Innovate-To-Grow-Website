import {act, renderHook, waitFor} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';

import type {ProjectGridRow} from '@/features/projects/api';
import {PROJECT_LIST_LOAD_ERROR, useRevalidatingRows} from '@/features/projects/hooks/useRevalidatingRows';

type Load = (signal: AbortSignal) => Promise<ProjectGridRow[]>;

const row = (project_title: string): ProjectGridRow => ({
  id: project_title,
  semester_label: '2026 Fall',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'CAP-101',
  project_title,
  organization: 'Org',
  industry: 'Energy',
  abstract: '',
  student_names: '',
  is_presenting: '',
});

/** A load whose answers the test gives, one request at a time. */
const deferredLoad = () => {
  const requests: Array<{signal: AbortSignal; resolve: (rows: ProjectGridRow[]) => void; reject: (error: unknown) => void}> =
    [];
  const load = vi.fn<Load>(
    (signal) =>
      new Promise((resolve, reject) => {
        requests.push({signal, resolve, reject});
      }),
  );
  return {load, requests};
};

const titles = (rows: ProjectGridRow[]) => rows.map((item) => item.project_title);

describe('useRevalidatingRows', () => {
  it('serves the rows it has while the same source reloads, then the new ones', async () => {
    const {load, requests} = deferredLoad();
    const {result} = renderHook(() => useRevalidatingRows(load));

    expect(result.current.loading).toBe(true);
    await act(async () => requests[0].resolve([row('First')]));
    expect(titles(result.current.rows)).toEqual(['First']);

    act(() => result.current.refetch());
    expect(result.current).toMatchObject({loading: false, error: null});
    expect(titles(result.current.rows)).toEqual(['First']);

    await act(async () => requests[1].resolve([row('First'), row('Second')]));
    expect(titles(result.current.rows)).toEqual(['First', 'Second']);
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("serves nothing of another source's rows while a new source loads", async () => {
    const past = deferredLoad();
    const all = deferredLoad();
    const {result, rerender} = renderHook(({load}) => useRevalidatingRows(load), {initialProps: {load: past.load}});
    await act(async () => past.requests[0].resolve([row('Archive only')]));

    rerender({load: all.load});

    // A search table seeds its rows once, so stale rows of the wrong list would stay in it.
    expect(result.current).toMatchObject({rows: [], loading: true, error: null});
    await waitFor(() => expect(all.load).toHaveBeenCalledTimes(1));
    await act(async () => all.requests[0].resolve([row('Current'), row('Archive only')]));
    expect(result.current.loading).toBe(false);
    expect(titles(result.current.rows)).toEqual(['Current', 'Archive only']);
  });

  it("keeps none of another source's rows when the new source fails to load", async () => {
    const past = deferredLoad();
    const all = deferredLoad();
    const {result, rerender} = renderHook(({load}) => useRevalidatingRows(load), {initialProps: {load: past.load}});
    await act(async () => past.requests[0].resolve([row('Archive only')]));

    rerender({load: all.load});
    await waitFor(() => expect(all.load).toHaveBeenCalledTimes(1));
    await act(async () => all.requests[0].reject(new Error('Network Error')));

    expect(result.current).toMatchObject({rows: [], loading: false, error: PROJECT_LIST_LOAD_ERROR});
  });

  it('keeps the rows next to the error when a reload of the same source fails', async () => {
    const {load, requests} = deferredLoad();
    const {result} = renderHook(() => useRevalidatingRows(load));
    await act(async () => requests[0].resolve([row('First')]));
    const firstRows = result.current.rows;

    act(() => result.current.refetch());
    await act(async () => requests[1].reject(new Error('Request failed with status code 503')));

    expect(result.current.rows).toBe(firstRows);
    expect(result.current).toMatchObject({loading: false, error: PROJECT_LIST_LOAD_ERROR});
  });

  it('aborts the request of a source it leaves, and ignores its late answer', async () => {
    const past = deferredLoad();
    const all = deferredLoad();
    const {result, rerender} = renderHook(({load}) => useRevalidatingRows(load), {initialProps: {load: past.load}});

    rerender({load: all.load});
    expect(past.requests[0].signal.aborted).toBe(true);
    await act(async () => past.requests[0].resolve([row('Too late')]));

    expect(result.current).toMatchObject({rows: [], loading: true});
  });

  it('loads nothing while disabled', () => {
    const {load} = deferredLoad();
    const {result} = renderHook(() => useRevalidatingRows(load, false));

    expect(result.current).toEqual({rows: [], loading: false, error: null, refetch: expect.any(Function)});
    expect(load).not.toHaveBeenCalled();
  });
});
