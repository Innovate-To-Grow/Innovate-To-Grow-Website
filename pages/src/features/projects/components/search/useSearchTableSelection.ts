import {useEffect, useMemo} from 'react';
import {stripProjectGridItem, type ProjectGridRow} from '../projectGrid';
import type {useSearchTableRows} from './useSearchTableRows';
import type {useSearchTableSave} from './useSearchTableSave';

interface UseSearchTableSelectionOptions {
  table: ReturnType<typeof useSearchTableRows>['table'];
  save: ReturnType<typeof useSearchTableSave>;
  tableId: string;
  title: string;
  onSelectionChange?: (tableId: string, rows: ProjectGridRow[], title: string) => void;
}

/**
 * The table's checked rows: how many there are (and how many the search hides), checking them, and
 * telling the page which checked rows this table has not submitted yet.
 */
export function useSearchTableSelection({table, save, tableId, title, onSelectionChange}: UseSearchTableSelectionOptions) {
  const shownKeys = useMemo(() => new Set(table.filteredRows.map((row) => row.__key)), [table.filteredRows]);
  const selectedCount = table.selectedRows.length;
  const hiddenSelectedCount = table.selectedRows.filter((row) => !shownKeys.has(row.__key)).length;
  const pendingSelection = useMemo(
    () => table.selectedRows.filter((row) => !save.inFlightKeys.has(row.__key)).map(stripProjectGridItem),
    [save.inFlightKeys, table.selectedRows],
  );

  useEffect(() => {
    onSelectionChange?.(tableId, pendingSelection, title);
    return () => onSelectionChange?.(tableId, [], title);
  }, [onSelectionChange, pendingSelection, tableId, title]);

  const handleToggleSelected = (rowKey: string) => {
    save.clearSaveStatus();
    table.toggleSelected(rowKey);
  };

  // Header checkbox and "Select All" act on the rows the current search shows (all rows when there is
  // no search), never on rows hidden by it, so a filtered "select all, uncheck a few" saves what it shows.
  const handleToggleSelectAllShown = () => {
    save.clearSaveStatus();
    const shown = table.filteredRows;
    if (shown.length > 0 && shown.every((row) => table.selectedKeys.has(row.__key))) {
      table.removeFromSelection(shown.map((row) => row.__key));
    } else {
      table.addToSelection(shown);
    }
  };

  return {selectedCount, hiddenSelectedCount, handleToggleSelected, handleToggleSelectAllShown};
}
