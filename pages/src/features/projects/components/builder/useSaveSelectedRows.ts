import {useCallback, useEffect, useRef, useState, type RefObject} from 'react';
import {hydrateProjectGridRowsSettled, needsProjectGridHydration} from '@/features/projects/api';
import {createProjectGridRowMatcher, type ProjectGridRow} from '../projectGrid';
import type {SearchTableSaveHelpers, SearchTableSaveResult} from '../search/types';
import {describeMergeResult, planMerge, type PendingSelection, type SelectionOutcome} from './mergeSelection';
import {findScrollAnchor, type ScrollAnchor} from './scrollAnchor';
import type {CurationDraftState} from './useCurationDraft';

interface UseSaveSelectedRowsOptions {
  draft: CurationDraftState;
  /** Set to the element to keep in place on screen when a save commits. */
  scrollAnchorRef: RefObject<ScrollAnchor | null>;
  onMessage: (message: string) => void;
}

/**
 * Save = merge a single search table's checked rows into the saved results. Projects already saved
 * (by id or content fingerprint) are skipped so each is stored once; compact archive rows load their
 * details first. The outcome goes back to the table that saved, which shows it beside its Save button.
 */
export function useSaveSelectedRows({draft, scrollAnchorRef, onMessage}: UseSaveSelectedRowsOptions) {
  const {mergedRowsRef, accountSequenceRef, appendRows} = draft;
  // Saves still loading project details. Sharing waits for them, or the share would leave out their rows.
  const [savesInFlight, setSavesInFlight] = useState(0);
  const saveControllers = useRef(new Set<AbortController>());
  // The rows each search table has checked but not submitted, to point out selections another table left
  // unsaved.
  const pendingSelections = useRef(new Map<string, PendingSelection>());

  // Leaving the page cancels the detail requests of saves still in flight.
  useEffect(() => {
    const controllers = saveControllers.current;
    return () => {
      controllers.forEach((controller) => controller.abort());
      controllers.clear();
    };
  }, []);

  const handleSelectionChange = useCallback((tableId: string, selectedRows: ProjectGridRow[], title: string) => {
    if (selectedRows.length) {
      pendingSelections.current.set(tableId, {rows: selectedRows, title});
    } else {
      pendingSelections.current.delete(tableId);
    }
  }, []);

  const mergeLoadedRows = useCallback(
    (
      loadedRows: ProjectGridRow[],
      outcome: SelectionOutcome,
      startedInAccount: number,
      tableId: string,
    ): SearchTableSaveResult => {
      onMessage('');
      if (startedInAccount !== accountSequenceRef.current) {
        return {
          tone: 'error',
          message: 'Your sign-in changed while saving, so nothing was saved. Your selection is kept.',
          retainedIndexes: loadedRows.map((_, index) => index),
        };
      }
      const plan = planMerge(loadedRows, outcome, mergedRowsRef.current);
      if (plan.rowsToAppend.length) {
        scrollAnchorRef.current = findScrollAnchor(tableId);
        appendRows(plan.rowsToAppend);
      }
      return describeMergeResult(plan, outcome, {
        tableId,
        totalSaved: mergedRowsRef.current.length,
        pendingSelections: pendingSelections.current,
      });
    },
    [accountSequenceRef, appendRows, mergedRowsRef, onMessage, scrollAnchorRef],
  );

  const handleMergeSelected = useCallback(
    (
      selected: ProjectGridRow[],
      {tableId, reportProgress}: SearchTableSaveHelpers,
    ): SearchTableSaveResult | Promise<SearchTableSaveResult> => {
      const startedInAccount = accountSequenceRef.current;
      const saved = createProjectGridRowMatcher(mergedRowsRef.current);
      const presaved = selected.flatMap((row, index) => (saved.has(row) ? [index] : []));
      // Only compact archive rows not saved yet need a detail request. Complete rows (AI results,
      // restored drafts) and already-saved projects are handled within the click.
      const loadIndexes = selected.flatMap((row, index) =>
        needsProjectGridHydration(row) && !saved.has(row) ? [index] : [],
      );
      if (!loadIndexes.length) {
        return mergeLoadedRows(selected, {failed: [], unavailable: [], presaved}, startedInAccount, tableId);
      }

      const controller = new AbortController();
      saveControllers.current.add(controller);
      setSavesInFlight((count) => count + 1);
      return hydrateProjectGridRowsSettled(
        loadIndexes.map((index) => selected[index]),
        {signal: controller.signal, onProgress: reportProgress},
      )
        .then(({rows: loadedRows, failedIndexes, unavailableIndexes}) => {
          const rowsWithDetails = [...selected];
          loadIndexes.forEach((selectedIndex, loadedIndex) => {
            rowsWithDetails[selectedIndex] = loadedRows[loadedIndex];
          });
          return mergeLoadedRows(
            rowsWithDetails,
            {
              failed: failedIndexes.map((loadedIndex) => loadIndexes[loadedIndex]),
              unavailable: unavailableIndexes.map((loadedIndex) => loadIndexes[loadedIndex]),
              presaved,
            },
            startedInAccount,
            tableId,
          );
        })
        .finally(() => {
          saveControllers.current.delete(controller);
          setSavesInFlight((count) => count - 1);
        });
    },
    [accountSequenceRef, mergeLoadedRows, mergedRowsRef],
  );

  return {savesInFlight, handleSelectionChange, handleMergeSelected};
}
