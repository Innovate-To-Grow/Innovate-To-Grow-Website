import '../../styles/cascade/projects.css';
import {useRef} from 'react';
import {LoadingIndicator} from '@/components/LoadingIndicator';
import {ProjectGridControls} from '../controls/ProjectGridControls';
import {useDetailsAnnouncements} from '../state/useDetailsAnnouncements';
import {useResultsFocus} from '../state/useResultsFocus';
import {useRetryFocus} from '../state/useRetryFocus';
import type {ProjectGridTableProps} from '../contracts/gridTableProps';
import {withGridDefaults} from './resolvedGridProps';
import {PageControls, ProjectGridResults} from './ProjectGridTableBody';

export type {ProjectGridSortOption} from '../contracts/gridTableProps';

/**
 * The projects grid: a filter well, an optional toolbar, the results (a table on wide screens, a list on
 * phones) and the pager. Paging, sorting and selection state come from `useProjectGridTable`.
 */
export const ProjectGridTable = (props: ProjectGridTableProps) => {
  const grid = withGridDefaults(props);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const details = useDetailsAnnouncements(grid);
  const countRef = useRef<HTMLParagraphElement>(null);
  const emptyRef = useRef<HTMLElement>(null);
  const {loadingRef, retryRef, retry} = useRetryFocus(Boolean(grid.loading), grid.error, countRef, emptyRef);
  const resultsFocus = useResultsFocus(countRef, emptyRef, grid.serverSearch?.addedRowsKey ?? null);
  const {onRetry} = grid;
  const toolbarElement = grid.toolbar ? (
    <div className={`project-grid-toolbar${grid.toolbarPlacement === 'bottom' ? ' project-grid-toolbar--bottom' : ''}`}>
      {grid.toolbar}
    </div>
  ) : null;

  return (
    <div className="project-grid-table-shell" onFocus={resultsFocus.onFocus} onBlur={resultsFocus.onBlur}>
      {/* Always in the page, so each new message is read out (a polite live region, like the count line). */}
      <p className="sr-only" aria-live="polite">
        {details.message}
      </p>

      <ProjectGridControls
        search={grid.search}
        searchControl={grid.searchControl}
        controlsStatus={grid.controlsStatus}
        searchPlaceholder={grid.searchPlaceholder}
        searchLabel={grid.searchLabel}
        filterControls={grid.filterControls}
        onSearchChange={grid.onSearchChange}
        pageControls={
          grid.sortOptions ? null : <PageControls grid={grid} onToggleAllDetails={details.toggleAllDetails} />
        }
        searchInputRef={searchInputRef}
      />

      {grid.toolbarPlacement === 'top' ? toolbarElement : null}

      {grid.loading ? (
        // Focusable from script: it holds focus while Try Again loads the rows (useRetryFocus).
        <p ref={loadingRef} className="project-grid-state project-grid-state-loading" role="status" tabIndex={-1}>
          <LoadingIndicator label="Loading project data…" />
        </p>
      ) : null}
      {grid.error ? (
        <div className="project-grid-load-error">
          <p className="project-grid-state project-grid-state-error itg-error" role="alert">
            {grid.error}
          </p>
          {onRetry ? (
            <button
              ref={retryRef}
              type="button"
              className="itg-btn itg-btn-outline"
              onClick={() => retry(onRetry)}
            >
              Try Again
            </button>
          ) : null}
        </div>
      ) : null}

      {!grid.loading && !grid.error ? (
        <ProjectGridResults
          grid={grid}
          details={details}
          searchInputRef={searchInputRef}
          countRef={countRef}
          emptyRef={emptyRef}
        />
      ) : null}

      {grid.toolbarPlacement === 'bottom' ? toolbarElement : null}
    </div>
  );
};
