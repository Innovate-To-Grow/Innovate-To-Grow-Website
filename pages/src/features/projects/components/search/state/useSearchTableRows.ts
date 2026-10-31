import {useCallback, useLayoutEffect, useRef, useState} from 'react';
import {useProjectCatalog} from '@/features/projects/catalog/projectCatalog';
import {createProjectGridItems, type ProjectGridItem, type ProjectGridRow} from '../../grid/contracts/projectGrid';
import {useProjectGridTable} from '../../grid/state/useProjectGridTable';

/**
 * A search table's own rows — trimmed with "Remove from Table" / "Keep Only Selected" and restored with
 * a one-step undo — and the paged, searchable table over them.
 */
export function useSearchTableRows(initialRows: ProjectGridRow[], tableId: string, initialSearch?: string) {
  const [rows, setRows] = useState<ProjectGridItem[]>(() => createProjectGridItems(initialRows, tableId));
  const [undoRows, setUndoRows] = useState<ProjectGridItem[] | null>(null);
  const [resetCount, setResetCount] = useState(0);
  // The rows and reset count as last rendered, for a save that finishes after a reload replaced the rows.
  const rowsRef = useRef(rows);
  const resetCountRef = useRef(resetCount);
  const {searchRemote} = useProjectCatalog();
  const table = useProjectGridTable({
    rows,
    pageSize: 5,
    defaultSortField: 'semester_label',
    defaultSortDirection: 'desc',
    initialSearch,
    // The rows come without their abstracts; the server's search over the page's list (ProjectCatalog) reads those too.
    searchRemote,
  });

  // Synced during commit, so a save resolving right after a reset already sees the new rows.
  useLayoutEffect(() => {
    rowsRef.current = rows;
    resetCountRef.current = resetCount;
  }, [resetCount, rows]);

  /** Replace the rows with a reload and start the table over (search, sort, selection). */
  const reload = (nextRows: ProjectGridRow[]) => {
    setResetCount((count) => count + 1);
    setRows(createProjectGridItems(nextRows, tableId));
    setUndoRows(null);
    table.reset();
  };

  const removeSelected = useCallback(() => {
    if (!table.hasSelection) {
      return;
    }
    const nextRows = table.removeSelectedRows(rows);
    if (nextRows.length === rows.length) {
      table.clearSelection();
      return;
    }
    setUndoRows(rows);
    setRows(nextRows);
    table.clearSelection();
  }, [rows, table]);

  // Trims the table to the checked rows and keeps them checked, so Add to Curation works right away.
  const keepSelected = useCallback(() => {
    if (!table.hasSelection) {
      return;
    }
    const nextRows = table.keepSelectedRows(rows);
    if (nextRows.length === rows.length) {
      return;
    }
    setUndoRows(rows);
    setRows(nextRows);
  }, [rows, table]);

  const undo = useCallback(() => {
    if (!undoRows) {
      return;
    }
    setRows(undoRows);
    setUndoRows(null);
    table.clearSelection();
  }, [table, undoRows]);

  return {
    rows,
    table,
    rowsRef,
    resetCountRef,
    canUndo: Boolean(undoRows),
    reload,
    removeSelected,
    keepSelected,
    undo,
  };
}

export type SearchTableRows = ReturnType<typeof useSearchTableRows>;
