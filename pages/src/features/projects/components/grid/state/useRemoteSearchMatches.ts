import {useEffect, useState} from 'react';

/**
 * Resolves to the ids of the projects whose text, as the server holds it, matches `query`, or to null when the
 * server declines a query too broad to narrow the list (see searchPastProjectArchiveIds).
 */
export type RemoteRowSearch = (query: string, signal: AbortSignal) => Promise<ReadonlySet<string> | null>;

/** How long typing must pause before the server is asked. */
export const REMOTE_SEARCH_DELAY_MS = 300;
// A shorter query already matches much of the archive by the rows' own text; the server is not asked for it.
const MIN_REMOTE_QUERY_LENGTH = 3;
// The longest search the archive endpoint accepts.
const MAX_REMOTE_QUERY_LENGTH = 200;

interface RemoteAnswer {
  query: string;
  /** null when the request failed or was declined: the search then finds what the rows' own text finds. */
  ids: ReadonlySet<string> | null;
}

/**
 * Rows a search finds by text the rows do not carry. Compact archive rows leave out the abstract, which the server
 * does search: once typing pauses, the server is asked for the query, and its matches come back for that query only.
 * `pending` stays true until the server has answered the current query.
 */
export function useRemoteSearchMatches(search: string, searchRemote?: RemoteRowSearch) {
  const query = search.replace(/\s+/g, ' ').trim();
  const asks =
    Boolean(searchRemote) && query.length >= MIN_REMOTE_QUERY_LENGTH && query.length <= MAX_REMOTE_QUERY_LENGTH;
  const [answer, setAnswer] = useState<RemoteAnswer | null>(null);

  useEffect(() => {
    if (!asks || !searchRemote) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      searchRemote(query, controller.signal).then(
        (ids) => {
          if (!controller.signal.aborted) setAnswer({query, ids});
        },
        () => {
          if (!controller.signal.aborted) setAnswer({query, ids: null});
        },
      );
    }, REMOTE_SEARCH_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [asks, query, searchRemote]);

  const current = asks && answer?.query === query ? answer : null;
  return {matches: current?.ids ?? null, pending: asks && !current};
}
