import type {PastProjectsStatusTone} from '../builder/PastProjectsAIStatus';
import type {ProjectGridRow} from '../projectGrid';

/** Outcome of saving a table's checked rows, shown inside the table that saved them. */
export interface SearchTableSaveResult {
  tone: Exclude<PastProjectsStatusTone, 'loading'>;
  message: string;
  /**
   * Indexes into the submitted rows that were not saved and stay checked (e.g. their details failed to load).
   * Every other submitted row is unchecked. An error result without it keeps every submitted row checked.
   */
  retainedIndexes?: number[];
}

export interface SearchTableSaveHelpers {
  /** The table that is saving, so the caller can tell it apart from the others. */
  tableId: string;
  /** Report detail-loading progress while a save runs. */
  reportProgress: (done: number, total: number) => void;
}

export type SaveOutcome = SearchTableSaveResult | void;
/** Which Save button was pressed: the one above the table, or the one under a long page. */
export type SaveOrigin = 'top' | 'bottom';

export type MergeSelectedHandler = (
  rows: ProjectGridRow[],
  helpers: SearchTableSaveHelpers,
) => SaveOutcome | PromiseLike<SaveOutcome>;

export interface SaveProgress {
  count: number;
  done: number;
  total: number;
}
