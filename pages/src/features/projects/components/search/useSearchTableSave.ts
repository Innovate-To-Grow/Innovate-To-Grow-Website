import {useCallback, useRef, useState} from 'react';
import {createProjectGridRowMatcher, stripProjectGridItem, type ProjectGridItem} from '../projectGrid';
import type {SearchTableRows} from './useSearchTableRows';
import type {
  MergeSelectedHandler,
  SaveOrigin,
  SaveOutcome,
  SaveProgress,
  SearchTableSaveResult,
} from './types';

const SAVE_FAILED_MESSAGE = 'Could not save the selected projects. They are still selected, so you can try again.';
// Saving this many rows at once is almost always an accidental "select everything"; ask first.
const LARGE_SAVE_THRESHOLD = 100;
// Progress is shown for saves that load this many details, updated in tenths so it does not flood.
const PROGRESS_MIN_TOTAL = 20;

const isPromiseLike = <T,>(value: unknown): value is PromiseLike<T> =>
  typeof (value as {then?: unknown} | null | undefined)?.then === 'function';

/** Indexes of submitted rows that stay checked: those the outcome retains, or all of them after a plain failure. */
const retainedIndexes = (submitted: ProjectGridItem[], outcome: SaveOutcome): Set<number> => {
  const keepsAll = outcome?.tone === 'error' && !outcome.retainedIndexes;
  return new Set(keepsAll ? submitted.map((_, index) => index) : (outcome?.retainedIndexes ?? []));
};

/** The outcome message, noting retained rows that the reloaded table no longer has. */
const withMissingNote = (message: string, missing: number) =>
  missing && message
    ? `${message} ${missing === 1 ? 'One of them is' : `${missing} of them are`} not in the reloaded table.`
    : message;

/** Progress updates for large detail loads only, in tenths so they do not flood. */
const throttledProgress =
  (count: number, setSaveProgress: (progress: SaveProgress) => void) => (done: number, total: number) => {
    const step = Math.max(1, Math.floor(total / 10));
    if (total >= PROGRESS_MIN_TOTAL && (done === total || done % step === 0)) {
      setSaveProgress({count, done, total});
    }
  };

/** A large save waiting for the user to confirm it; confirming runs it unless saving got disabled meanwhile. */
function useLargeSaveConfirmation(
  runSave: (submitted: ProjectGridItem[], origin: SaveOrigin) => Promise<void>,
  mergeDisabled: boolean,
) {
  const [pendingLargeSave, setPendingLargeSave] = useState<{rows: ProjectGridItem[]; origin: SaveOrigin} | null>(null);
  const confirmLargeSave = () => {
    if (!pendingLargeSave) return;
    const {rows: submitted, origin} = pendingLargeSave;
    setPendingLargeSave(null);
    if (!mergeDisabled) {
      void runSave(submitted, origin);
    }
  };
  return {pendingLargeSave, setPendingLargeSave, confirmLargeSave};
}

interface UseSearchTableSaveOptions {
  tableId: string;
  tableRows: SearchTableRows;
  mergeDisabled: boolean;
  onMergeSelected: MergeSelectedHandler;
}

/**
 * Saving a table's checked rows: one save at a time, a confirmation for very large ones, detail-loading
 * progress, and the outcome. Rows submitted by a save stay checked (and are reported as in flight) until it
 * settles; only the ones it saved are then unchecked.
 */
export function useSearchTableSave({tableId, tableRows, mergeDisabled, onMergeSelected}: UseSearchTableSaveOptions) {
  const {table, rowsRef, resetCountRef} = tableRows;
  const [isSaving, setIsSaving] = useState(false);
  const [saveProgress, setSaveProgress] = useState<SaveProgress | null>(null);
  const [saveStatus, setSaveStatus] = useState<SearchTableSaveResult | null>(null);
  const [saveOrigin, setSaveOrigin] = useState<SaveOrigin>('top');
  // Rows submitted by the save in flight: still checked, but no longer waiting for the user to save them.
  const [inFlightKeys, setInFlightKeys] = useState<ReadonlySet<string>>(() => new Set());
  const isSavingRef = useRef(false);

  // Uncheck only what was submitted and not retained: a failed save keeps its rows checked for a retry,
  // and rows checked while the save ran are not wiped. If the table was reloaded meanwhile, the retained rows
  // are checked again among the new rows.
  const finishSave = useCallback(
    (submitted: ProjectGridItem[], outcome: SaveOutcome, startedAtReset: number) => {
      const retained = retainedIndexes(submitted, outcome);
      table.removeFromSelection(submitted.filter((_, index) => !retained.has(index)).map((row) => row.__key));
      let message = outcome?.message ?? '';
      if (resetCountRef.current !== startedAtReset && retained.size) {
        const retainedRows = submitted.filter((_, index) => retained.has(index));
        const isRetained = createProjectGridRowMatcher(retainedRows).has;
        const inNewRows = createProjectGridRowMatcher(rowsRef.current).has;
        table.addToSelection(rowsRef.current.filter(isRetained));
        message = withMissingNote(message, retainedRows.filter((row) => !inNewRows(row)).length);
      }
      setSaveStatus(outcome && message ? {...outcome, message} : null);
    },
    [resetCountRef, rowsRef, table],
  );

  const runSave = useCallback(
    async (submitted: ProjectGridItem[], origin: SaveOrigin) => {
      const failure: SearchTableSaveResult = {tone: 'error', message: SAVE_FAILED_MESSAGE};
      const startedAtReset = resetCountRef.current;
      setSaveOrigin(origin);
      let pending: SaveOutcome | PromiseLike<SaveOutcome>;
      try {
        pending = onMergeSelected(submitted.map(stripProjectGridItem), {
          tableId,
          reportProgress: throttledProgress(submitted.length, setSaveProgress),
        });
      } catch {
        finishSave(submitted, failure, startedAtReset);
        return;
      }
      // A save that needs no network finishes in this click; only a pending one shows the in-flight state.
      if (!isPromiseLike<SaveOutcome>(pending)) {
        finishSave(submitted, pending, startedAtReset);
        return;
      }

      isSavingRef.current = true;
      setIsSaving(true);
      setInFlightKeys(new Set(submitted.map((row) => row.__key)));
      setSaveStatus(null);
      setSaveProgress({count: submitted.length, done: 0, total: 0});
      let outcome: SaveOutcome;
      try {
        outcome = await pending;
      } catch {
        outcome = failure;
      } finally {
        isSavingRef.current = false;
        setIsSaving(false);
        setInFlightKeys(new Set());
        setSaveProgress(null);
      }
      finishSave(submitted, outcome, startedAtReset);
    },
    [finishSave, onMergeSelected, resetCountRef, tableId],
  );

  const {pendingLargeSave, setPendingLargeSave, confirmLargeSave} = useLargeSaveConfirmation(runSave, mergeDisabled);

  const saveSelected = (origin: SaveOrigin) => {
    if (!table.hasSelection || isSavingRef.current || mergeDisabled) {
      return;
    }
    const submitted = table.selectedRows;
    if (submitted.length > LARGE_SAVE_THRESHOLD) {
      setPendingLargeSave({rows: submitted, origin});
      return;
    }
    void runSave(submitted, origin);
  };

  /** A reload drops a pending confirmation; a running save keeps its outcome slot. */
  const onTableReload = () => {
    setPendingLargeSave(null);
    if (!isSaving) {
      setSaveStatus(null);
    }
  };

  return {
    isSaving,
    saveProgress,
    saveStatus,
    saveOrigin,
    inFlightKeys,
    pendingLargeSave,
    // A save's outcome stays up until the user starts a new selection in this table.
    clearSaveStatus: () => setSaveStatus(null),
    saveSelected,
    confirmLargeSave,
    cancelLargeSave: () => setPendingLargeSave(null),
    onTableReload,
  };
}

export type SearchTableSave = ReturnType<typeof useSearchTableSave>;
