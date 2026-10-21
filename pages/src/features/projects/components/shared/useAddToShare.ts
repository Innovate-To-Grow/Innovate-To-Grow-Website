import {useCallback, useEffect, useRef, useState} from 'react';
import {hydrateProjectGridRowsSettled, needsProjectGridHydration} from '@/features/projects/api';
import {createProjectGridRowMatcher, type ProjectGridRow} from '../projectGrid';
import {describeSaveResult} from '../saveResults';
import type {SearchTableSaveHelpers, SearchTableSaveResult} from '../search/types';

// The share API refuses more rows than this (PastProjectShareSerializer.validate_rows).
const MAX_SHARED_ROWS = 1000;

interface UseAddToShareOptions {
  /** The rows the shared page holds now. */
  currentRows: ProjectGridRow[];
  isAlreadyShared: (row: ProjectGridRow) => boolean;
  /** Adds the rows to the share; may resolve to how many were actually appended (others were already there). */
  onAddRows: (rows: ProjectGridRow[]) => Promise<number | void>;
  onMessage: (message: string) => void;
}

/**
 * "Add Selected" on a shared page: add one search table's checked rows to the share. Projects already in
 * it (by id or fingerprint) are skipped so each project is stored once, and compact archive rows load their
 * details first. The outcome is reported inside the table that added them.
 */
export function useAddToShare({currentRows, isAlreadyShared, onAddRows, onMessage}: UseAddToShareOptions) {
  const [isSaving, setIsSaving] = useState(false);
  const saveControllers = useRef(new Set<AbortController>());

  // Leaving the page cancels the detail requests of an add still in flight.
  useEffect(() => {
    const controllers = saveControllers.current;
    return () => {
      controllers.forEach((controller) => controller.abort());
      controllers.clear();
    };
  }, []);

  const addSelected = useCallback(
    async (selected: ProjectGridRow[], {reportProgress}: SearchTableSaveHelpers): Promise<SearchTableSaveResult> => {
      // Projects already shared need no detail request.
      const toAdd = selected.flatMap((row, index) => (isAlreadyShared(row) ? [] : [index]));
      if (currentRows.length + toAdd.length > MAX_SHARED_ROWS) {
        return {
          tone: 'error',
          message: `A shared page can include at most ${MAX_SHARED_ROWS} projects. Select fewer projects and try again.`,
        };
      }

      const controller = new AbortController();
      saveControllers.current.add(controller);
      setIsSaving(true);
      onMessage('');
      try {
        // Archive rows arrive compact, with no abstract or student names. Saving them as they are
        // would write those fields away as blank for everyone who opens the share, and the detail
        // endpoint is the only place that content lives. Fill them in first, as the builder does.
        const pendingRows = toAdd.map((index) => selected[index]);
        const {rows: loadedRows, failedIndexes, unavailableIndexes} = pendingRows.some(needsProjectGridHydration)
          ? await hydrateProjectGridRowsSettled(pendingRows, {signal: controller.signal, onProgress: reportProgress})
          : {rows: pendingRows, failedIndexes: [] as number[], unavailableIndexes: [] as number[]};

        const skipped = new Set([...failedIndexes, ...unavailableIndexes]);
        const shared = createProjectGridRowMatcher(currentRows);
        const rowsToAppend: ProjectGridRow[] = [];
        let alreadyAdded = selected.length - toAdd.length;
        loadedRows.forEach((row, index) => {
          if (skipped.has(index)) {
            return;
          }
          if (shared.has(row)) {
            alreadyAdded += 1;
            return;
          }
          shared.add(row);
          rowsToAppend.push(row);
        });

        const appended = rowsToAppend.length ? await onAddRows(rowsToAppend) : 0;
        const added = typeof appended === 'number' ? appended : rowsToAppend.length;
        const result = describeSaveResult(
          {
            added,
            alreadySaved: alreadyAdded + (rowsToAppend.length - added),
            failed: failedIndexes.length,
            unavailable: unavailableIndexes.length,
          },
          {added: 'added.', already: 'in this shared result', place: 'in this shared result', retryLabel: 'Add Selected'},
        );
        return {...result, retainedIndexes: failedIndexes.map((index) => toAdd[index])};
      } catch {
        // Keep the user's selection so they can retry without re-checking rows.
        return {
          tone: 'error',
          message: 'Unable to add selected projects. They are still selected, so you can try again.',
        };
      } finally {
        saveControllers.current.delete(controller);
        setIsSaving(false);
      }
    },
    [currentRows, isAlreadyShared, onAddRows, onMessage],
  );

  return {isSaving, addSelected};
}
