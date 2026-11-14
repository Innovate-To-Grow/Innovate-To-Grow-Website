import {MergedListGrid, NarrowedSearchHint} from '../list/MergedListGrid';
import {BuilderCardHeader} from '../list/MergedListHeader';
import {useStatusLineInView} from '../list/useStatusLineInView';
import {type BuilderMergedListProps, useBuilderList} from './useBuilderList';
import {BuilderListFooter, BuilderListToolbar} from './BuilderListParts';

export type {BuilderMergedListProps} from './useBuilderList';

/**
 * The builder's unsaved merged list. Saving, exports and bulk removal act on the rows the search
 * shows; while a curation is being saved the rows stay as they were at the click.
 */
export const BuilderMergedList = (props: BuilderMergedListProps) => {
  const {id, className, rows, recentlyAdded, pendingSaveCount, title, onCreateShare, onDeleteRows} = props;
  const {isAuthenticated, canShare, list, noteInsert, hiddenAddedCount, curation, saveButton, signIn, ...actions} =
    useBuilderList(props);
  const {table, headingId} = list;
  const shownCount = table.filteredRows.length;
  const {cardRef, lineRef, onPointerDown} = useStatusLineInView(list.statusMessage, list.statusReports);

  return (
    <section
      ref={cardRef}
      id={id}
      className={`itg-panel project-grid-card project-grid-merged${className ? ` ${className}` : ''}`}
      aria-labelledby={headingId}
      onPointerDown={onPointerDown}
    >
      <BuilderCardHeader
        headingId={headingId}
        title={title}
        rowCount={rows.length}
        canSave={Boolean(onCreateShare)}
        isAuthenticated={isAuthenticated}
        saveButton={saveButton}
        signIn={signIn}
      />

      {shownCount < rows.length ? (
        <NarrowedSearchHint
          shownCount={shownCount}
          totalCount={rows.length}
          hiddenAddedCount={hiddenAddedCount}
          onClearSearch={() => table.setSearch('')}
        />
      ) : null}

      <MergedListGrid
        table={table}
        rows={rows}
        title={title}
        sharedMode={false}
        highlightedKeys={recentlyAdded?.keys}
        onDeleteRow={actions.handleDeleteRow}
        deleteDisabled={curation.isSharing}
        // Checkbox-based bulk removal: "check rows → Remove Selected".
        selectable={Boolean(onDeleteRows)}
        toolbar={
          <BuilderListToolbar
            list={list}
            rows={rows}
            title={title}
            canShare={canShare}
            curation={curation}
            onDeleteRows={onDeleteRows}
            canUndoRows={props.canUndoRows}
            onUndoRows={props.onUndoRows}
            onResetRows={props.onResetRows}
          />
        }
      />

      {/* Right under the table and its toolbar, where removing, undoing and exporting happen, and scrolled into
          view for them. Always in the page, so screen readers announce its first message too. */}
      <p ref={lineRef} className="project-grid-status" role="status">
        {list.statusMessage}
      </p>

      <BuilderListFooter
        list={list}
        curation={curation}
        isAuthenticated={isAuthenticated}
        showSaveSection={Boolean(onCreateShare)}
        noteInsert={noteInsert}
        saveButton={saveButton}
        pendingSaveCount={pendingSaveCount}
        signIn={signIn}
        onConfirmBulkAction={actions.handleConfirmBulkAction}
      />
    </section>
  );
};
