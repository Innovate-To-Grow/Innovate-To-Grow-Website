import '../../styles/cascade/projects.css';
import {useMemo} from 'react';
import {useProjectCatalog} from '@/features/projects/catalog/projectCatalog';
import {PastProjectsBuilder} from '../../builder/composition/PastProjectsBuilder';
import {MyCurationsPanel} from '../../curations/panel/MyCurationsPanel';
import {getEarliestTermYear, type ProjectGridRow} from '../../grid/contracts/projectGrid';
import type {PastProjectShareCreationResult} from '../../merged/composition/MergedResultsTable';

interface CatalogBuilderViewProps {
  rows: ProjectGridRow[];
  loading: boolean;
  error: string | null;
  /** Seeds the first search table's search (the page's `?value=`). */
  initialSearch: string;
  onRefreshRows: () => void;
  onCreateShare: (rows: ProjectGridRow[], name: string, note: string) => Promise<PastProjectShareCreationResult>;
}

/**
 * Body of /past-projects and /all-projects: the heading, meta line and lede of the list in context
 * (useProjectCatalog), the member's saved curations, and the builder that searches the list.
 */
export const CatalogBuilderView = ({
  rows,
  loading,
  error,
  initialSearch,
  onRefreshRows,
  onCreateShare,
}: CatalogBuilderViewProps) => {
  const {title, lede} = useProjectCatalog();
  const sinceYear = useMemo(() => getEarliestTermYear(rows), [rows]);
  const meta = rows.length
    ? `${rows.length} ${rows.length === 1 ? 'project' : 'projects'}${sinceYear ? ` since ${sinceYear}` : ''}`
    : '';

  return (
    // Marked so the chat launcher tucks away over the page's text and cards, not only its controls (useLauncherYield).
    <div className="past-projects-page" data-launcher-avoid="">
      <header className="past-projects-header" data-embed-section="page-header">
        <h1 className="itg-page-title">{title}</h1>
        {/* Its line is there while the list loads too: arriving later, it pushed the lede and the whole builder
            down (most of the page's layout shift). */}
        <p className="itg-page-meta" aria-hidden={meta ? undefined : true}>
          {meta || '\u00a0'}
        </p>
        <p className="itg-lead">{lede}</p>
      </header>

      <MyCurationsPanel />

      <PastProjectsBuilder
        rows={rows}
        loading={loading}
        error={error}
        initialSearch={initialSearch}
        onRefreshRows={onRefreshRows}
        onCreateShare={onCreateShare}
      />
    </div>
  );
};
