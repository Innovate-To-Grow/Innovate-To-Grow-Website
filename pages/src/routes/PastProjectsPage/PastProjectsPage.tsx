import {useEffect, useMemo, useRef, useState} from 'react';
import {useNavigate, useParams} from 'react-router';
import {
  MergedResultsTable,
  PastProjectsBuilder,
  SharedPastProjectMergeSearch,
  createProjectGridItems,
} from '@/features/projects';
import {usePastProjectGridData, usePastProjectShareData} from '@/features/projects/hooks/useProjectGridData';
import {
  createPastProjectShare,
  fetchPastProjectShare,
  updatePastProjectShare,
  type PastProjectShare,
  type ProjectGridRow,
} from '@/features/projects/api';

type PastProjectSharePatch = Partial<
  Pick<PastProjectShare, 'name' | 'rows' | 'note'>
>;

const PROJECT_ROW_FIELDS: Array<keyof ProjectGridRow> = [
  'id',
  'semester_label',
  'class_code',
  'team_number',
  'team_name',
  'project_title',
  'organization',
  'industry',
  'abstract',
  'student_names',
  'is_presenting',
];

const haveEqualRows = (
  left: ProjectGridRow[],
  right: ProjectGridRow[],
) =>
  left.length === right.length &&
  left.every((row, index) =>
    PROJECT_ROW_FIELDS.every(
      (field) => row[field] === right[index]?.[field],
    ),
  );

const rebaseSubmittedRows = (
  currentRows: ProjectGridRow[],
  baselineRows: ProjectGridRow[],
  submittedRows: ProjectGridRow[],
) => {
  const baselineById = new Map(baselineRows.map((row) => [row.id, row]));
  const submittedById = new Map(submittedRows.map((row) => [row.id, row]));
  const removedIds = new Set(
    baselineRows
      .filter((row) => !submittedById.has(row.id))
      .map((row) => row.id),
  );
  const changedFieldsById = new Map<
    ProjectGridRow['id'],
    Partial<ProjectGridRow>
  >();

  for (const submitted of submittedRows) {
    const baseline = baselineById.get(submitted.id);
    if (!baseline) continue;
    const changed: Partial<ProjectGridRow> = {};
    for (const field of PROJECT_ROW_FIELDS) {
      if (submitted[field] !== baseline[field]) {
        Object.assign(changed, {[field]: submitted[field]});
      }
    }
    if (Object.keys(changed).length > 0) {
      changedFieldsById.set(submitted.id, changed);
    }
  }

  let rebased = currentRows
    .filter((row) => !removedIds.has(row.id))
    .map((row) => ({
      ...row,
      ...(changedFieldsById.get(row.id) ?? {}),
    }));
  const currentIds = new Set(rebased.map((row) => row.id));
  for (const submitted of submittedRows) {
    if (!baselineById.has(submitted.id) && !currentIds.has(submitted.id)) {
      rebased.push(submitted);
      currentIds.add(submitted.id);
    }
  }

  const baselineSurvivorOrder = baselineRows
    .filter((row) => submittedById.has(row.id))
    .map((row) => row.id);
  const submittedBaselineOrder = submittedRows
    .filter((row) => baselineById.has(row.id))
    .map((row) => row.id);
  if (
    baselineSurvivorOrder.some(
      (id, index) => submittedBaselineOrder[index] !== id,
    )
  ) {
    const rebasedById = new Map(rebased.map((row) => [row.id, row]));
    const requestedIds = new Set(submittedBaselineOrder);
    rebased = [
      ...submittedBaselineOrder.flatMap((id) => {
        const row = rebasedById.get(id);
        return row ? [row] : [];
      }),
      ...rebased.filter((row) => !requestedIds.has(row.id)),
    ];
  }

  return rebased;
};

const isStaleSnapshotConflict = (error: unknown) => {
  if (!error || typeof error !== 'object') return false;
  const response = (error as {response?: unknown}).response;
  if (!response || typeof response !== 'object') return false;
  const status = (response as {status?: unknown}).status;
  const data = (response as {data?: unknown}).data;
  return (
    status === 409 &&
    Boolean(
      data &&
        typeof data === 'object' &&
        (data as {code?: unknown}).code === 'stale_snapshot',
    )
  );
};

const SHARE_CONFLICT_RELOADED =
  'This shared page changed elsewhere. The latest version was reloaded; review it before editing again.';
const SHARE_CONFLICT_RELOADING =
  'This shared page changed elsewhere. Reloading the latest version before any more edits are applied.';
const SHARE_CONFLICT_RELOAD_FAILED =
  'This shared page changed elsewhere, and the latest version could not be reloaded. Reload the page before editing again.';

export const PastProjectsPage = () => {
  const {shareId} = useParams<{shareId: string}>();
  const navigate = useNavigate();
  const sharedMode = Boolean(shareId);
  const {share, loading: shareLoading, error: shareError} = usePastProjectShareData(shareId);
  const [editableShare, setEditableShare] = useState<PastProjectShare | null>(null);
  // Reset the local override to the freshly fetched share whenever `share` changes identity.
  // This is the render-phase equivalent of the old `useEffect(() => setEditableShare(share), [share])`
  // (https://react.dev/learn/you-might-not-need-an-effect#adjusting-some-state-when-a-prop-changes):
  // `activeShare` already falls back to `share` when the override is stale, so the rendered output is
  // unchanged, but this avoids the effect's extra cascading commit.
  const [prevShare, setPrevShare] = useState(share);
  if (share !== prevShare) {
    setPrevShare(share);
    setEditableShare(share);
  }
  const activeShare = editableShare?.id === shareId ? editableShare : share;
  const [shareConflict, setShareConflict] = useState<{
    shareId: string;
    message: string;
  } | null>(null);
  const mutationQueueRef = useRef<Promise<unknown>>(Promise.resolve());
  const mutationEpochRef = useRef(0);
  const mutationShareIdRef = useRef(shareId);
  const latestShareRef = useRef<PastProjectShare | null>(activeShare);
  const mutationBlockedRef = useRef(false);

  useEffect(() => {
    if (mutationShareIdRef.current !== shareId) {
      mutationShareIdRef.current = shareId;
      mutationEpochRef.current += 1;
      mutationQueueRef.current = Promise.resolve();
      latestShareRef.current = null;
      mutationBlockedRef.current = false;
    }
    if (
      activeShare &&
      (latestShareRef.current?.id !== activeShare.id ||
        activeShare.version >= latestShareRef.current.version)
    ) {
      latestShareRef.current = activeShare;
    }
  }, [activeShare, shareId]);

  const {rows, loading, error, refetch} = usePastProjectGridData(!sharedMode || Boolean(activeShare?.can_edit));

  const sharedItems = useMemo(
    () => createProjectGridItems(activeShare?.rows || [], `shared-${shareId || 'past-projects'}`),
    [activeShare?.rows, shareId],
  );

  const handleCreateShare = async (shareRows: typeof rows, name: string, note: string) => {
    const nextShare = await createPastProjectShare(shareRows, name, note);
    setEditableShare(nextShare);
    navigate(`/past-projects/${nextShare.id}`);
    return nextShare;
  };

  const enqueueShareMutation = (
    buildPatch: (current: PastProjectShare) => PastProjectSharePatch,
  ): Promise<PastProjectShare> => {
    const targetShareId = shareId;
    const queuedEpoch = mutationEpochRef.current;
    const operation = mutationQueueRef.current.then(async () => {
      if (
        !targetShareId ||
        mutationShareIdRef.current !== targetShareId ||
        mutationEpochRef.current !== queuedEpoch ||
        mutationBlockedRef.current
      ) {
        throw new Error(SHARE_CONFLICT_RELOAD_FAILED);
      }

      const current = latestShareRef.current;
      if (!current || current.id !== targetShareId) {
        throw new Error('Shared past projects are not loaded yet.');
      }

      const patch = buildPatch(current);
      if (Object.keys(patch).length === 0) return current;

      try {
        const updated = await updatePastProjectShare(targetShareId, {
          ...patch,
          version: current.version,
        });
        if (
          mutationShareIdRef.current !== targetShareId ||
          mutationEpochRef.current !== queuedEpoch
        ) {
          throw new Error('The shared page changed while this update was running.');
        }
        latestShareRef.current = updated;
        mutationBlockedRef.current = false;
        setEditableShare(updated);
        setShareConflict(null);
        return updated;
      } catch (mutationError) {
        if (
          !isStaleSnapshotConflict(mutationError) ||
          mutationShareIdRef.current !== targetShareId
        ) {
          throw mutationError;
        }

        // Invalidate every mutation that was queued from the stale snapshot.
        // Those payloads must never be replayed over the newly fetched version.
        mutationEpochRef.current += 1;
        mutationBlockedRef.current = true;
        setShareConflict({
          shareId: targetShareId,
          message: SHARE_CONFLICT_RELOADING,
        });

        try {
          const authoritative = await fetchPastProjectShare(targetShareId);
          if (mutationShareIdRef.current === targetShareId) {
            latestShareRef.current = authoritative;
            mutationBlockedRef.current = false;
            setEditableShare(authoritative);
            setShareConflict({
              shareId: targetShareId,
              message: SHARE_CONFLICT_RELOADED,
            });
          }
        } catch {
          if (mutationShareIdRef.current === targetShareId) {
            setShareConflict({
              shareId: targetShareId,
              message: SHARE_CONFLICT_RELOAD_FAILED,
            });
          }
        }

        throw new Error(SHARE_CONFLICT_RELOADED, {cause: mutationError});
      }
    });

    mutationQueueRef.current = operation.then(
      () => undefined,
      () => undefined,
    );
    return operation;
  };

  const handleUpdateShare = async (shareRows: ProjectGridRow[], name: string, note: string) => {
    if (!activeShare) {
      throw new Error('Shared past projects are not loaded yet.');
    }
    const baseline = activeShare;
    const rowsChanged = !haveEqualRows(shareRows, baseline.rows);
    await enqueueShareMutation((current) => {
      const patch: PastProjectSharePatch = {};
      if (rowsChanged) {
        const rebasedRows = rebaseSubmittedRows(
          current.rows,
          baseline.rows,
          shareRows,
        );
        if (!haveEqualRows(rebasedRows, current.rows)) {
          patch.rows = rebasedRows;
        }
      }
      if (name !== baseline.name) patch.name = name;
      if (note !== baseline.note) patch.note = note;
      return patch;
    });
  };

  const handleAddShareRows = async (rowsToAdd: ProjectGridRow[]) => {
    if (!activeShare) {
      throw new Error('Shared past projects are not loaded yet.');
    }
    await enqueueShareMutation((current) => ({
      rows: [...current.rows, ...rowsToAdd],
    }));
  };

  return (
    <div className="past-projects-page">
      <header className="past-projects-hero">
        <h1 className="past-projects-title">Past Projects</h1>
        {!sharedMode ? (
          <p className="past-projects-lead">
            Search across past Innovate to Grow projects, keep only the items you want, merge the selected results into
            a shareable archive, and curate the results.
          </p>
        ) : null}
      </header>

      {sharedMode ? (
        <>
          {shareLoading ? <div className="past-projects-state">Loading shared results...</div> : null}
          {shareError ? <div className="past-projects-state past-projects-state-error">{shareError}</div> : null}
          {shareConflict && shareConflict.shareId === shareId ? (
            <div
              className="past-projects-state past-projects-state-error"
              role="alert"
            >
              {shareConflict.message}
            </div>
          ) : null}
          {!shareLoading && !shareError ? (
            <>
              <MergedResultsTable
                rows={sharedItems}
                sharedMode
                note={activeShare?.note}
                title={activeShare?.name?.trim() || 'Shared Past Project Results'}
                editable={Boolean(activeShare?.can_edit)}
                onUpdateShare={activeShare?.can_edit ? handleUpdateShare : undefined}
              />
              {activeShare?.can_edit ? (
                <SharedPastProjectMergeSearch
                  currentRows={activeShare.rows}
                  error={error}
                  loading={loading}
                  rows={rows}
                  onAddRows={handleAddShareRows}
                  onRefreshRows={refetch}
                />
              ) : null}
            </>
          ) : null}
        </>
      ) : (
        <PastProjectsBuilder
          rows={rows}
          loading={loading}
          error={error}
          onRefreshRows={refetch}
          onCreateShare={handleCreateShare}
        />
      )}
    </div>
  );
};
