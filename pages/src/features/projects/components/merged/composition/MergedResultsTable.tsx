import type {ProjectGridItem, ProjectGridRow} from '../../grid/contracts/projectGrid';
import {BuilderMergedList} from '../builder/BuilderMergedList';
import {SharedMergedList} from '../shared/SharedMergedList';
import type {PastProjectShareCreationResult} from '../builder/useCurationShare';
import type {ListMessage} from '../list/useMergedList';

export type {PastProjectShareCreationResult};

interface MergedResultsTableProps {
  id?: string;
  className?: string;
  rows: ProjectGridItem[];
  /** Rows added by the latest save (builder): highlighted, and the table pages to the first of them. */
  recentlyAdded?: {keys: ReadonlySet<string>; token: number} | null;
  /** Saves still loading their projects (builder). Sharing waits, or the link would leave those rows out. */
  pendingSaveCount?: number;
  /** The builder's latest report about its draft (a removal, an undo…), shown in the list's status line. */
  message?: ListMessage | null;
  sharedMode?: boolean;
  title?: string;
  note?: string;
  /** When the shared list was created (ISO 8601), for its meta line. */
  sharedAt?: string;
  editable?: boolean;
  onCreateShare?: (
    rows: ProjectGridRow[],
    name: string,
    note: string,
  ) => Promise<PastProjectShareCreationResult>;
  onUpdateShare?: (rows: ProjectGridRow[], name: string, note: string) => Promise<void>;
  /** The builder's unsaved curation name and note. Left out, the card keeps them itself. */
  nameDraft?: string;
  noteDraft?: string;
  onNameDraftChange?: (name: string) => void;
  onNoteDraftChange?: (note: string) => void;
  onDeleteRow?: (row: ProjectGridItem) => void;
  onDeleteRows?: (rows: ProjectGridItem[]) => void;
  canUndoRows?: boolean;
  onUndoRows?: () => void;
  onResetRows?: () => void;
}

/**
 * The merged past-project list, in two modes: the builder's unsaved list (save as a curation, bulk
 * remove, undo/reset) and a saved shared page (copy link, and — for its owner — rename, edit the note,
 * remove rows with undo). Both export the list as PDF / Excel / Word. Each mode lives in `merged/`.
 */
export const MergedResultsTable = ({
  sharedMode = false,
  title = 'Curation Draft',
  editable = false,
  canUndoRows = false,
  recentlyAdded = null,
  pendingSaveCount = 0,
  ...props
}: MergedResultsTableProps) =>
  sharedMode ? (
    <SharedMergedList
      id={props.id}
      className={props.className}
      rows={props.rows}
      title={title}
      note={props.note}
      sharedAt={props.sharedAt}
      editable={editable}
      onUpdateShare={props.onUpdateShare}
      canUndoRows={canUndoRows}
      onUndoRows={props.onUndoRows}
    />
  ) : (
    <BuilderMergedList
      id={props.id}
      className={props.className}
      rows={props.rows}
      recentlyAdded={recentlyAdded}
      pendingSaveCount={pendingSaveCount}
      title={title}
      message={props.message}
      onCreateShare={props.onCreateShare}
      nameDraft={props.nameDraft}
      noteDraft={props.noteDraft}
      onNameDraftChange={props.onNameDraftChange}
      onNoteDraftChange={props.onNoteDraftChange}
      onDeleteRow={props.onDeleteRow}
      onDeleteRows={props.onDeleteRows}
      canUndoRows={canUndoRows}
      onUndoRows={props.onUndoRows}
      onResetRows={props.onResetRows}
    />
  );
