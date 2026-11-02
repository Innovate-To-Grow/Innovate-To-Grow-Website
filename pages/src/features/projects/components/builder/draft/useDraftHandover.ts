import {useEffect, useEffectEvent, useRef} from 'react';
import {getProjectRowIds, type ProjectGridRow} from '../../grid/contracts/projectGrid';
import {isEmbeddedBuilder, readDraftHandover} from './draftHandover';

interface UseDraftHandoverOptions {
  /** The list the builder searches, where the handed-over ids are looked up. */
  rows: ProjectGridRow[];
  loading: boolean;
  /** Adds the rows that were found, each once; `missing` counts the ids the list does not have. */
  onHandover: (found: ProjectGridRow[], missing: number) => void;
}

/**
 * On the full page, takes the projects a widget handed over (see draftHandover.ts) into this browser's draft once
 * the list has loaded, and takes the handover out of the address, so a reload or a shared link does not add
 * them again. A current-semester project whose semester was archived meanwhile is found as the archive row that
 * stands in for it (and names its id in `current_project_id`).
 */
export function useDraftHandover({rows, loading, onHandover}: UseDraftHandoverOptions) {
  const pendingIds = useRef<string[] | null | undefined>(undefined);
  const handOver = useEffectEvent(onHandover);

  useEffect(() => {
    if (pendingIds.current === undefined) {
      pendingIds.current = isEmbeddedBuilder() ? null : readDraftHandover(window.location.hash);
    }
    const ids = pendingIds.current;
    // An unreadable handover is dropped at once; a readable one waits for the list.
    if (!ids || (ids.length && (loading || !rows.length))) {
      return;
    }
    pendingIds.current = null;
    // Keep the router's own history entry state; only the fragment goes.
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}`);
    if (!ids.length) {
      return;
    }
    const byId = new Map(rows.flatMap((row) => getProjectRowIds(row).map((id) => [id, row] as const)));
    const matches = ids.map((id) => byId.get(id));
    const found = [...new Set(matches.filter((row): row is ProjectGridRow => Boolean(row)))];
    handOver(found, matches.filter((row) => !row).length);
  }, [loading, rows]);
}
