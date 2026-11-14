import {type ReactNode} from 'react';
import {type ProjectGridRow} from '../../grid/contracts/projectGrid';
import type {MergeSelectedHandler} from '../state/types';

export interface SearchTableCardProps {
  canRemove: boolean;
  className?: string;
  description?: string;
  emptyMessage?: string;
  initialRows: ProjectGridRow[];
  /** Search to start the table with. */
  initialSearch?: string;
  /**
   * Changing it replaces the rows with `initialRows` and starts the table over (search, sort, selection), as a
   * reload (Refresh, new AI results). A save that is running carries on and reports its outcome here.
   */
  resetKey?: string | number;
  resultsMotionKey?: string | number;
  searchControl?: ReactNode;
  controlsStatus?: ReactNode;
  tableId: string;
  title: string;
  /** Label for the per-table merge button (e.g. "Add to Curation" in the builder). */
  mergeLabel?: string;
  /** Verb for the merge ("Add" -> "Add 120 Projects" in the large-save confirmation). */
  mergeVerb?: string;
  /** Verb shown while that merge runs ("Adding" -> "Adding…" / "Adding 3 projects…"). */
  mergingVerb?: string;
  /** Disable the merge button (e.g. while an async add from another table is in flight). */
  mergeDisabled?: boolean;
  /** Marks rows that are already in the saved results (e.g. with an "Added" chip). */
  isRowSaved?: (row: ProjectGridRow) => boolean;
  savedRowLabel?: string;
  /** Scroll to the saved results; offered next to a save's outcome. */
  onViewMergedResults?: () => void;
  viewMergedResultsLabel?: string;
  /**
   * Told which checked rows this table has not submitted yet, so the page can mention selections another
   * table left unsaved.
   */
  onSelectionChange?: (tableId: string, rows: ProjectGridRow[], title: string) => void;
  onRemove: (tableId: string) => void;
  onRefresh?: (tableId: string) => void;
  /**
   * Push this table's checked rows into the merged results, and resolve to a SearchTableSaveResult to report
   * the outcome inside this table. Submitted rows are unchecked afterwards except the retained ones, so rows
   * checked while a save runs stay checked.
   */
  onMergeSelected: MergeSelectedHandler;
}

export function withCardDefaults({
  description = 'Search this table, check the projects you want, then click Add to Curation to add them to the curation draft.',
  emptyMessage = 'No rows available in this search table.',
  mergeLabel = 'Add to Curation',
  mergeVerb = 'Add',
  mergingVerb = 'Adding',
  mergeDisabled = false,
  viewMergedResultsLabel = 'View Curation Draft',
  ...rest
}: SearchTableCardProps) {
  return {...rest, description, emptyMessage, mergeLabel, mergeVerb, mergingVerb, mergeDisabled, viewMergedResultsLabel};
}

export type CardProps = ReturnType<typeof withCardDefaults>;
