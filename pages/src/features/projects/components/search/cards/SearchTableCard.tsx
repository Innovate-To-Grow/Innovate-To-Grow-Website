import {useId, useState, type ReactNode} from 'react';
import {useMediaQuery} from '@/features/layout';
import {SaveStatusAnnouncer, VisibleSaveStatus} from '../controls/SaveStatus';
import {SaveControls, SearchTableToolbar} from '../controls/SearchTableToolbar';
import type {SaveOrigin} from '../state/types';
import {useSearchTableRows} from '../state/useSearchTableRows';
import {useSearchTableSave} from '../state/useSearchTableSave';
import {useSearchTableSelection} from '../state/useSearchTableSelection';
import {type SearchTableCardProps, withCardDefaults} from './searchTableCardProps';
import {
  LargeSaveDialog,
  SearchTableCardHeader,
  SearchTableGrid,
  SelectionAnnouncer,
} from './SearchTableCardParts';

export type {SearchTableSaveHelpers, SearchTableSaveResult} from '../state/types';

// Long pages get a second Save button under the table, where the eye is after checking rows.
const BOTTOM_ACTIONS_MIN_ROWS = 6;

/**
 * One search table of the past-projects builder: search the rows, check projects, and save them into the
 * merged results. Its rows (`search/state/useSearchTableRows`), selection (`search/state/useSearchTableSelection`)
 * and the save flow (`search/state/useSearchTableSave`) live in their own hooks.
 */
export function SearchTableCard(props: SearchTableCardProps) {
  const card = withCardDefaults(props);
  const {tableId, title, resetKey, mergeDisabled, mergingVerb} = card;
  const tableRows = useSearchTableRows(card.initialRows, tableId, card.initialSearch);
  const {table} = tableRows;
  const save = useSearchTableSave({tableId, tableRows, mergeDisabled, onMergeSelected: card.onMergeSelected});
  const selection = useSearchTableSelection({table, save, tableId, title, onSelectionChange: card.onSelectionChange});
  const [appliedResetKey, setAppliedResetKey] = useState(resetKey);
  const selectionHintId = useId();
  const headingId = useId();
  // Same breakpoint as the stacked table actions in projectsResponsive.css.
  const isPhone = useMediaQuery('(max-width: 768px)');

  if (resetKey !== appliedResetKey) {
    setAppliedResetKey(resetKey);
    tableRows.reload(card.initialRows);
    save.onTableReload();
  }

  const saveControls = (origin: SaveOrigin) => (
    <SaveControls
      origin={origin}
      save={save}
      hasSelection={table.hasSelection}
      selectedCount={selection.selectedCount}
      hiddenSelectedCount={selection.hiddenSelectedCount}
      mergeDisabled={mergeDisabled}
      mergeLabel={card.mergeLabel}
      mergingVerb={mergingVerb}
      selectionHintId={selectionHintId}
    />
  );

  // The visible box sits next to the Save button that was pressed, or the top one once the bottom one is gone
  // (the page got shorter than BOTTOM_ACTIONS_MIN_ROWS rows).
  const showBottomActions = table.pagedRows.length >= BOTTOM_ACTIONS_MIN_ROWS;
  const statusOrigin: SaveOrigin = save.saveOrigin === 'bottom' && showBottomActions ? 'bottom' : 'top';
  const hasVisibleStatus = Boolean(save.saveProgress || save.saveStatus);
  const statusFor = (origin: SaveOrigin): ReactNode =>
    hasVisibleStatus && statusOrigin === origin ? (
      <div className="search-table-save-status">
        <VisibleSaveStatus
          saveProgress={save.saveProgress}
          saveStatus={save.saveStatus}
          mergingVerb={mergingVerb}
          viewMergedResultsLabel={card.viewMergedResultsLabel}
          onViewMergedResults={card.onViewMergedResults}
        />
      </div>
    ) : null;
  const {onRefresh, resultsMotionKey} = card;

  return (
    // Named after its heading: with several tables open, each one's search field, pager and buttons are
    // announced inside "Search Table 2" rather than as one more unnamed "Search" or "Pages".
    <section
      className={`project-grid-card search-table-card${card.className ? ` ${card.className}` : ''}`}
      data-search-table-id={tableId}
      aria-labelledby={headingId}
      aria-busy={save.isSaving}
    >
      <SearchTableCardHeader card={card} headingId={headingId} isSaving={save.isSaving} />
      <p className="project-grid-card-copy">{card.description}</p>

      <SaveStatusAnnouncer saveProgress={save.saveProgress} saveStatus={save.saveStatus} mergingVerb={mergingVerb} />
      <SelectionAnnouncer selectedCount={selection.selectedCount} hiddenSelectedCount={selection.hiddenSelectedCount} />

      <div
        key={resultsMotionKey === undefined ? 'search-table-static-results' : `search-table-results-${resultsMotionKey}`}
        className={resultsMotionKey ? 'search-table-results-motion' : undefined}
      >
        <SearchTableGrid
          card={card}
          tableRows={tableRows}
          selection={selection}
          toolbar={
            <SearchTableToolbar
              tableRows={tableRows}
              save={save}
              saveControls={saveControls('top')}
              topStatus={statusFor('top')}
              isPhone={isPhone}
              saveGroupLabel={card.mergeLabel}
              selectionHintId={selectionHintId}
              onRefresh={onRefresh ? () => onRefresh(tableId) : undefined}
            />
          }
        />
        {showBottomActions ? (
          <div className="search-table-bottom-actions" role="group" aria-label={`${card.mergeLabel} below the table`}>
            <div className="project-grid-toolbar-cluster search-table-save-group">{saveControls('bottom')}</div>
            {statusFor('bottom')}
          </div>
        ) : null}
      </div>

      <LargeSaveDialog save={save} mergeVerb={card.mergeVerb} hiddenSelectedCount={selection.hiddenSelectedCount} />
    </section>
  );
}
