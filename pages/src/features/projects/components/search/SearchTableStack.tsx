import type {ComponentProps} from 'react';
import type {ProjectGridRow} from '../projectGrid';
import {SearchTableCard} from '../SearchTableCard';
import {PastProjectsAISearchForm} from '../builder/PastProjectsAISearchForm';
import {PastProjectsAIStatus} from '../builder/PastProjectsAIStatus';
import {initialSearchTableId, searchTableTitle, type useSearchTables} from './useSearchTables';

type SearchTableCardProps = ComponentProps<typeof SearchTableCard>;

/** Props every card in the stack shares (what saving does, how saved rows are marked). */
export type SharedCardProps = Pick<
  SearchTableCardProps,
  | 'mergeLabel'
  | 'mergeVerb'
  | 'mergingVerb'
  | 'mergeDisabled'
  | 'isRowSaved'
  | 'savedRowLabel'
  | 'onViewMergedResults'
  | 'onSelectionChange'
  | 'onMergeSelected'
>;

interface SearchTableStackProps {
  tables: ReturnType<typeof useSearchTables>;
  /** Table ids' prefix, as passed to useSearchTables. */
  idPrefix: string;
  rows: ProjectGridRow[];
  /** Seeds the first table's search. */
  initialSearch?: string;
  isAuthenticated: boolean;
  canRefresh: boolean;
  cardProps: SharedCardProps;
  copy: {
    aiDescription: string;
    /** Left out, the card's default description is used. */
    standardDescription?: string;
    noTablesMessage: string;
  };
}

export const SearchTableStack = ({
  tables,
  idPrefix,
  rows,
  initialSearch,
  isAuthenticated,
  canRefresh,
  cardProps,
  copy,
}: SearchTableStackProps) => {
  const {searchTables} = tables;
  return (
    <div className="search-table-stack">
      {searchTables.map((table) => {
        const isAISearchTable = table.type === 'ai';
        return (
          <SearchTableCard
            key={table.id}
            {...cardProps}
            resetKey={table.rowsResetKey}
            canRemove={searchTables.length > 1}
            description={isAISearchTable ? copy.aiDescription : copy.standardDescription}
            emptyMessage={isAISearchTable ? 'Run AI search to load projects into this table.' : undefined}
            initialRows={table.initialRows ?? rows}
            initialSearch={table.id === initialSearchTableId(idPrefix) ? initialSearch : undefined}
            controlsStatus={
              table.message && table.messageTone && table.messageTone !== 'loading' ? (
                <PastProjectsAIStatus message={table.message} tone={table.messageTone} />
              ) : undefined
            }
            searchControl={
              isAISearchTable ? (
                <PastProjectsAISearchForm
                  isAuthenticated={isAuthenticated}
                  loading={Boolean(table.isLoading)}
                  onSearch={(query) => tables.runAISearch(table.id, query)}
                />
              ) : undefined
            }
            tableId={table.id}
            title={searchTableTitle(table, searchTables)}
            className={
              isAISearchTable ? `is-ai-search-table${table.rowsResetKey ? ' has-ai-results' : ''}` : undefined
            }
            resultsMotionKey={isAISearchTable ? table.rowsResetKey : undefined}
            onRemove={tables.removeSearchTable}
            onRefresh={isAISearchTable || !canRefresh ? undefined : tables.refreshSearchTable}
          />
        );
      })}

      {!searchTables.length ? <p className="project-grid-empty project-grid-empty-shell">{copy.noTablesMessage}</p> : null}
    </div>
  );
};
