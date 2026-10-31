import {useNavigate, useSearchParams} from 'react-router';
import {createPastProjectShare, type ProjectGridRow} from '@/features/projects/api';
import {ALL_PROJECTS_CATALOG} from '@/features/projects/catalog/catalogs';
import {ProjectCatalogContext} from '@/features/projects/catalog/projectCatalog';
import {CatalogBuilderView} from '@/features/projects/components/views/pages/CatalogBuilderView';
import {useAllProjectGridData} from '@/features/projects/hooks/useProjectGridData';
import {usePageTitle} from '@/hooks/usePageTitle';

/**
 * `/all-projects`: the Past Projects builder over every project, the active schedule's teams that are not archived
 * yet and then the archive. It shares the curation draft, My Curations and the share pages with Past Projects: a
 * saved curation opens at `/past-projects/:shareId`, whose saved notice links back here (`builtOn`).
 */
export const AllProjectsPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  usePageTitle(ALL_PROJECTS_CATALOG.title);
  const {rows, loading, error, refetch} = useAllProjectGridData();

  const handleCreateShare = async (shareRows: ProjectGridRow[], name: string, note: string) => {
    const share = await createPastProjectShare(shareRows, name, note);
    navigate(`/past-projects/${share.id}`, {state: {curationSaved: true, builtOn: ALL_PROJECTS_CATALOG.path}});
    return share;
  };

  return (
    <ProjectCatalogContext.Provider value={ALL_PROJECTS_CATALOG}>
      <CatalogBuilderView
        rows={rows}
        loading={loading}
        error={error}
        initialSearch={searchParams.get('value') || ''}
        onRefreshRows={refetch}
        onCreateShare={handleCreateShare}
      />
    </ProjectCatalogContext.Provider>
  );
};
