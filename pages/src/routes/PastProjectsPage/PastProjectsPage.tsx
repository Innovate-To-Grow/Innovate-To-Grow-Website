import {useMemo, useState} from 'react';
import {useLocation, useNavigate, useParams, useSearchParams} from 'react-router';
import {useAuth} from '@/features/auth';
import {createProjectGridItems} from '@/features/projects';
import {ALL_PROJECTS_CATALOG, PAST_PROJECTS_CATALOG} from '@/features/projects/catalog/catalogs';
import {CatalogBuilderView} from '@/features/projects/components/views/pages/CatalogBuilderView';
import {
  useAllProjectGridData,
  usePastProjectGridData,
  usePastProjectShareData,
} from '@/features/projects/hooks/useProjectGridData';
import {createPastProjectShare, type ProjectGridRow} from '@/features/projects/api';
import {usePageTitle} from '@/hooks/usePageTitle';
import {SharedCurationView} from './SharedCurationView';
import {shareDisplayTitle, useSharedListMutations} from './useSharedListMutations';

/**
 * Whether the viewer may edit a curation (`can_edit`) is the server's answer for whoever was signed in when it
 * loaded. Signing out (or into another account) without a reload asks again, so the owner's controls go.
 */
function useReloadShareForNewViewer(reloadShare: () => void) {
  const viewerId = useAuth().user?.member_uuid ?? null;
  const [shareViewerId, setShareViewerId] = useState(viewerId);
  if (viewerId !== shareViewerId) {
    setShareViewerId(viewerId);
    reloadShare();
  }
}

/** The history state of a curation the builder just saved: All Projects' save names itself in `builtOn`. */
interface CurationSavedState {
  curationSaved?: boolean;
  builtOn?: string;
}

/** The builder a curation was saved from, which its saved notice names: Past Projects unless All Projects says so. */
const builtOnCatalog = (builtOn: unknown) =>
  builtOn === ALL_PROJECTS_CATALOG.path ? ALL_PROJECTS_CATALOG : PAST_PROJECTS_CATALOG;

/**
 * `/past-projects` (the builder) and `/past-projects/:shareId` (a saved curation's shared page, whichever builder
 * saved it). Edits to a shared page go through `useSharedListMutations`, which serializes them and reconciles
 * concurrent edits.
 */
export const PastProjectsPage = () => {
  const {shareId} = useParams<{shareId: string}>();
  const navigate = useNavigate();
  // Set by the builder's save, which opens the new curation's page.
  const savedState = useLocation().state as CurationSavedState | null;
  const justSaved = Boolean(savedState?.curationSaved);
  const [searchParams] = useSearchParams();
  const sharedMode = Boolean(shareId);
  const {
    share,
    loading: shareLoading,
    error: shareError,
    notFound: shareNotFound,
    retry: retryShare,
  } = usePastProjectShareData(shareId);
  useReloadShareForNewViewer(retryShare);
  const {activeShare, setEditableShare, conflictMessage, updateShare, addShareRows} = useSharedListMutations(
    shareId,
    share,
  );
  // A shared list is named after the share (its message pages name themselves). The builder names itself too: both
  // routes have the same route title, so coming back from a curation would otherwise keep that curation's title.
  usePageTitle(sharedMode ? activeShare && shareDisplayTitle(activeShare) : 'Past Projects');
  // A list is only needed to search: the builder searches the archive, and the owner adding to a shared list searches
  // every project, which holds whatever either builder saved.
  const archive = usePastProjectGridData(!sharedMode);
  const allProjects = useAllProjectGridData(sharedMode && Boolean(activeShare?.can_edit));

  const sharedItems = useMemo(
    () => createProjectGridItems(activeShare?.rows || [], `shared-${shareId || 'past-projects'}`),
    [activeShare?.rows, shareId],
  );

  const handleCreateShare = async (shareRows: ProjectGridRow[], name: string, note: string) => {
    const nextShare = await createPastProjectShare(shareRows, name, note);
    setEditableShare(nextShare);
    navigate(`/past-projects/${nextShare.id}`, {state: {curationSaved: true}});
    return nextShare;
  };

  if (sharedMode) {
    return (
      <SharedCurationView
        status={{loading: shareLoading, error: shareError, notFound: shareNotFound, retry: retryShare}}
        conflictMessage={conflictMessage}
        justSaved={justSaved}
        builtOn={builtOnCatalog(savedState?.builtOn)}
        share={activeShare}
        items={sharedItems}
        onUpdateShare={updateShare}
        projects={allProjects}
        onAddRows={addShareRows}
      />
    );
  }

  return (
    <CatalogBuilderView
      rows={archive.rows}
      loading={archive.loading}
      error={archive.error}
      initialSearch={searchParams.get('value') || ''}
      onRefreshRows={archive.refetch}
      onCreateShare={handleCreateShare}
    />
  );
};
