import {useEffect, useEffectEvent, useRef} from 'react';
import type {ProjectGridRow} from '../../grid/contracts/projectGrid';
import {isEmbeddedBuilder, readDraftHandover} from './draftHandover';

interface UseDraftHandoverOptions {
  /** The past-project archive, where the handed-over ids are looked up. */
  rows: ProjectGridRow[];
  loading: boolean;
  /** Adds the archive rows that were found; `missing` counts the ids the archive does not have. */
  onHandover: (found: ProjectGridRow[], missing: number) => void;
}

/**
 * On the full page, takes the projects a widget handed over (see draftHandover.ts) into this browser's draft once
 * the archive has loaded, and takes the handover out of the address, so a reload or a shared link does not add
 * them again.
 */
export function useDraftHandover({rows, loading, onHandover}: UseDraftHandoverOptions) {
  const pendingIds = useRef<string[] | null | undefined>(undefined);
  const handOver = useEffectEvent(onHandover);

  useEffect(() => {
    if (pendingIds.current === undefined) {
      pendingIds.current = isEmbeddedBuilder() ? null : readDraftHandover(window.location.hash);
    }
    const ids = pendingIds.current;
    // An unreadable handover is dropped at once; a readable one waits for the archive.
    if (!ids || (ids.length && (loading || !rows.length))) {
      return;
    }
    pendingIds.current = null;
    // Keep the router's own history entry state; only the fragment goes.
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}`);
    if (!ids.length) {
      return;
    }
    const byId = new Map(rows.flatMap((row) => (row.id ? [[row.id, row] as const] : [])));
    const found = ids.flatMap((id) => byId.get(id) ?? []);
    handOver(found, ids.length - found.length);
  }, [loading, rows]);
}
