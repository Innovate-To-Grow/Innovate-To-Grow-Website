import {useId, useMemo, useState} from 'react';
import {stripProjectGridItem, type ProjectGridItem} from '../projectGrid';
import {useProjectGridTable} from '../useProjectGridTable';
import type {PendingBulkAction} from './MergedEditButtons';

/** State both list modes share: the paged table, the status line and the pending bulk-action dialog. */
export function useMergedList(rows: ProjectGridItem[], sharedMode: boolean) {
  const table = useProjectGridTable({
    rows,
    pageSize: 5,
    defaultSortField: 'semester_label',
    defaultSortDirection: 'desc',
    expandAllByDefault: sharedMode,
  });
  const [statusMessage, setStatusMessage] = useState('');
  const [pendingBulkAction, setPendingBulkAction] = useState<PendingBulkAction | null>(null);
  const headingId = useId();
  // The full saved snapshot — used by title/note/delete saves and by the shared-mode export.
  const allRows = useMemo(() => rows.map(stripProjectGridItem), [rows]);
  // The visible (filtered/sorted) rows — used for builder share-create and builder export.
  const visibleRows = useMemo(() => table.sortedRows.map(stripProjectGridItem), [table.sortedRows]);

  return {
    table,
    allRows,
    visibleRows,
    headingId,
    statusMessage,
    setStatusMessage,
    pendingBulkAction,
    setPendingBulkAction,
  };
}

/**
 * After a save, move to the page holding the first newly added row (the table sorts by semester, so
 * older projects otherwise land on a later page and the save looks like it did nothing). Returns how
 * many of the new rows the current search hides.
 */
export function useRevealRecentlyAdded(
  table: ReturnType<typeof useProjectGridTable>,
  rows: ProjectGridItem[],
  recentlyAdded: {keys: ReadonlySet<string>; token: number} | null,
) {
  const [revealedToken, setRevealedToken] = useState(recentlyAdded?.token ?? null);
  if (recentlyAdded && recentlyAdded.token !== revealedToken) {
    setRevealedToken(recentlyAdded.token);
    const firstAddedIndex = table.sortedRows.findIndex((row) => recentlyAdded.keys.has(row.__key));
    if (firstAddedIndex >= 0) {
      table.setPage(Math.floor(firstAddedIndex / table.pageSize));
    }
  }
  if (!recentlyAdded) {
    return 0;
  }
  const shownKeys = new Set(table.filteredRows.map((row) => row.__key));
  return rows.filter((row) => recentlyAdded.keys.has(row.__key) && !shownKeys.has(row.__key)).length;
}
