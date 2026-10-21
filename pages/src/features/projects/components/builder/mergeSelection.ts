import {createProjectGridRowMatcher, type ProjectGridItem, type ProjectGridRow} from '../projectGrid';
import {describeSaveResult, pluralize} from '../saveResults';
import type {SearchTableSaveResult} from '../search/types';

/** Indexes (into the selection) of rows that were not loaded, or that were already saved at the click. */
export interface SelectionOutcome {
  failed: number[];
  unavailable: number[];
  presaved: number[];
}

export interface MergePlan {
  rowsToAppend: ProjectGridRow[];
  alreadySaved: number;
  /** Presaved rows removed from the saved results while this save ran. */
  removedMeanwhile: number[];
  /** Every saved project after this merge (for counting other tables' unsaved selections). */
  saved: ReturnType<typeof createProjectGridRowMatcher>;
}

/**
 * Dedup against the merged rows as committed now, not as they were when Save was clicked: another save,
 * Reset or Remove may have landed meanwhile. Rows that were already saved at the click were not loaded, so
 * they are never appended. One removed from the saved results meanwhile stays removed, rather than a copy
 * without abstract or students taking its place, and stays checked so it can be saved again.
 */
export function planMerge(
  loadedRows: ProjectGridRow[],
  {failed, unavailable, presaved}: SelectionOutcome,
  currentRows: ProjectGridItem[],
): MergePlan {
  const saved = createProjectGridRowMatcher(currentRows);
  const removedMeanwhile = presaved.filter((index) => !saved.has(loadedRows[index]));
  const skipped = new Set([...failed, ...unavailable, ...presaved]);
  const rowsToAppend: ProjectGridRow[] = [];
  let alreadySaved = presaved.length - removedMeanwhile.length;
  loadedRows.forEach((row, index) => {
    if (skipped.has(index)) {
      return;
    }
    if (saved.has(row)) {
      alreadySaved += 1;
      return;
    }
    saved.add(row);
    rowsToAppend.push(row);
  });
  return {rowsToAppend, alreadySaved, removedMeanwhile, saved};
}

export interface PendingSelection {
  rows: ProjectGridRow[];
  title: string;
}

// Each table saves only its own checked rows; say so when other tables still hold checked rows that are not saved.
export const describeUnsavedSelections = (tables: Array<{count: number; title: string}>) => {
  if (!tables.length) {
    return '';
  }
  if (tables.length === 1) {
    const [{count, title}] = tables;
    return `${title} still has ${pluralize(count, 'selected project')} that ${count === 1 ? 'is' : 'are'} not saved yet.`;
  }
  const titles = tables.map((table) => table.title);
  return `${titles.slice(0, -1).join(', ')} and ${titles.at(-1)} still have selected projects that are not saved yet.`;
};

/** The message and still-checked rows the saving table shows beside its Save button. */
export function describeMergeResult(
  plan: MergePlan,
  outcome: SelectionOutcome,
  context: {tableId: string; totalSaved: number; pendingSelections: Map<string, PendingSelection>},
): SearchTableSaveResult {
  const {tone, message} = describeSaveResult(
    {
      added: plan.rowsToAppend.length,
      alreadySaved: plan.alreadySaved,
      failed: outcome.failed.length,
      unavailable: outcome.unavailable.length,
    },
    {
      added: `added to Saved Merged Results (${context.totalSaved} in total).`,
      already: 'saved',
      place: 'in Saved Merged Results',
      retryLabel: 'Save Selected',
    },
  );
  const removed = plan.removedMeanwhile.length;
  const removedNote = removed
    ? `${pluralize(removed, 'project')} ${removed === 1 ? 'was' : 'were'} removed from Saved Merged ` +
      `Results while saving and ${removed === 1 ? 'is' : 'are'} still selected.`
    : '';
  // Checked rows another table holds that are not saved now (this save may have saved some of them).
  const unsavedElsewhere = describeUnsavedSelections(
    [...context.pendingSelections].flatMap(([id, selection]) => {
      const count = id === context.tableId ? 0 : selection.rows.filter((row) => !plan.saved.has(row)).length;
      return count ? [{count, title: selection.title}] : [];
    }),
  );
  return {
    tone,
    message: [message, removedNote, tone !== 'error' ? unsavedElsewhere : ''].filter(Boolean).join(' '),
    retainedIndexes: [...outcome.failed, ...plan.removedMeanwhile].sort((left, right) => left - right),
  };
}
