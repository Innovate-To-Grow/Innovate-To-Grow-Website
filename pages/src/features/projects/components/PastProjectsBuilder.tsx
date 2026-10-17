import {useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState} from 'react';
import {useAuth} from '@/features/auth';
import {buildLoginPath} from '@/features/auth/api/redirects';
import {
    hydrateProjectGridRowsSettled,
    needsProjectGridHydration,
    searchPastProjectsWithAI,
    toProjectGridRow,
} from '@/features/projects/api';
import {PastProjectsAIStatus} from './builder/PastProjectsAIStatus';
import {PastProjectsAISearchForm} from './builder/PastProjectsAISearchForm';
import {PastProjectsActionBar} from './builder/PastProjectsActionBar';
import {PastProjectsDialog} from './builder/PastProjectsDialog';
import {MergedResultsTable, type PastProjectShareCreationResult} from './MergedResultsTable';
import {SearchTableCard, type SearchTableSaveHelpers, type SearchTableSaveResult} from './SearchTableCard';
import {
    createProjectGridFingerprint,
    createProjectGridItems,
    stripProjectGridItem,
    type ProjectGridItem,
    type ProjectGridRow,
} from './projectGrid';

const INITIAL_SEARCH_TABLE: SearchTableState = {id: 'search-table-1', type: 'standard'};

const AI_SEARCH_LIMIT = 10;

// The merged results live in component state, but creating a share requires signing in, and the
// login button navigates away with a full-page reload (window.location) — which would wipe an
// in-progress merge. Persist the merged rows in sessionStorage so they survive the login
// round-trip (and any reload) within the tab; they are restored on mount and dropped once a share
// is successfully created. sessionStorage (not localStorage) keeps the draft scoped to the tab
// session, so it does not leak into a later, unrelated visit.
const MERGED_ROWS_STORAGE_KEY = 'past-projects:builder:merged-rows';

const readPersistedMergedRows = (): ProjectGridRow[] => {
    try {
        const raw = sessionStorage.getItem(MERGED_ROWS_STORAGE_KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? (parsed as ProjectGridRow[]) : [];
    } catch {
        return [];
    }
};

const writePersistedMergedRows = (rows: ProjectGridRow[]) => {
    try {
        if (rows.length) {
            sessionStorage.setItem(MERGED_ROWS_STORAGE_KEY, JSON.stringify(rows));
        } else {
            sessionStorage.removeItem(MERGED_ROWS_STORAGE_KEY);
        }
    } catch {
        // sessionStorage can throw (private mode / quota / disabled) — degrade to in-memory only.
    }
};

const clearPersistedMergedRows = () => {
    try {
        sessionStorage.removeItem(MERGED_ROWS_STORAGE_KEY);
    } catch {
        // ignore — nothing to clean up if storage is unavailable.
    }
};

const MERGED_RESULTS_ID = 'past-projects-saved-results';

const pluralize = (count: number, noun: string) => `${count} ${noun}${count === 1 ? '' : 's'}`;

// The outcome of one table's save, worded for the table that saved it.
const describeSaveResult = ({
    added,
    alreadySaved,
    failed,
    unavailable,
    total,
}: {
    added: number;
    alreadySaved: number;
    failed: number;
    unavailable: number;
    total: number;
}): Pick<SearchTableSaveResult, 'tone' | 'message'> => {
    const parts: string[] = [];
    if (added) {
        parts.push(`${pluralize(added, 'project')} added to Saved Merged Results (${total} in total).`);
    }
    if (alreadySaved) {
        parts.push(
            added || failed || unavailable
                ? `${pluralize(alreadySaved, 'project')} ${alreadySaved === 1 ? 'was' : 'were'} already saved.`
                : `${alreadySaved === 1 ? 'That project is' : 'Those projects are'} already in Saved Merged Results.`,
        );
    }
    if (unavailable) {
        parts.push(
            `${pluralize(unavailable, 'project')} ${unavailable === 1 ? 'is' : 'are'} no longer in the archive ` +
                `and ${unavailable === 1 ? 'was' : 'were'} skipped.`,
        );
    }
    if (failed) {
        parts.push(
            `${pluralize(failed, 'project')} could not be loaded and ${failed === 1 ? 'is' : 'are'} still selected. ` +
                'Click Save Selected to try again.',
        );
    }
    return {tone: failed || (unavailable && !added) ? 'error' : added ? 'success' : 'info', message: parts.join(' ')};
};

// Each table saves only its own checked rows; say so when other tables still hold checked rows.
const describeUnsavedSelections = (tables: Array<{count: number; title: string}>) => {
    if (!tables.length) {
        return '';
    }
    if (tables.length === 1) {
        const [{count, title}] = tables;
        return `${title} still has ${pluralize(count, 'selected project')} that ${count === 1 ? 'is' : 'are'} not saved yet.`;
    }
    const titles = tables.map((table) => table.title);
    return `${titles.slice(0, -1).join(', ')} and ${titles.at(-1)} still have selected projects that are not saved yet.`;
};

// New rows are added to the snapshot an Undo/Reset restores, so a save that lands after a Reset is
// neither lost by a later Undo nor allowed to cancel that Undo.
const appendUnsaved = (snapshot: ProjectGridItem[], added: ProjectGridItem[]) => {
    const ids = new Set(snapshot.flatMap((row) => (row.id ? [row.id] : [])));
    const fingerprints = new Set(snapshot.map((row) => createProjectGridFingerprint(stripProjectGridItem(row))));
    return [
        ...snapshot,
        ...added.filter(
            (row) =>
                !(row.id && ids.has(row.id)) && !fingerprints.has(createProjectGridFingerprint(stripProjectGridItem(row))),
        ),
    ];
};

const createAISearchTableTitle = (query: string) => {
    const normalized = query.trim().replace(/\s+/g, ' ');
    const clipped = normalized.length > 54 ? `${normalized.slice(0, 51).trim()}...` : normalized;
    return `AI Search Table: ${clipped}`;
};

const getAISearchErrorMessage = (error: unknown) => {
    const payload = (error as { response?: { data?: { detail?: string; message?: string } } }).response?.data;
    return payload?.detail || payload?.message || 'AI search is unavailable right now. Please try again.';
};

interface PastProjectsBuilderProps {
    error: string | null;
    loading: boolean;
    rows: ProjectGridRow[];
    onRefreshRows?: () => void;
    onCreateShare: (
        rows: ProjectGridRow[],
        name: string,
        note: string,
    ) => Promise<PastProjectShareCreationResult>;
}

interface SearchTableState {
    id: string;
    initialRows?: ProjectGridRow[];
    isLoading?: boolean;
    message?: string;
    messageTone?: 'error' | 'loading' | 'success';
    rowsResetKey?: number;
    title?: string;
    type: 'standard' | 'ai';
}

export const PastProjectsBuilder = ({
                                        error,
                                        loading,
                                        rows,
                                        onRefreshRows,
                                        onCreateShare,
                                    }: PastProjectsBuilderProps) => {
    const {isAuthenticated, isInitializing, unverified, user} = useAuth();
    const memberId = user?.member_uuid ?? null;
    const [searchTables, setSearchTables] = useState<SearchTableState[]>(() => [INITIAL_SEARCH_TABLE]);
    // Seed from any draft persisted before a login reload so the merged results survive the round-trip.
    const [mergedRows, setMergedRows] = useState<ProjectGridItem[]>(() =>
        createProjectGridItems(readPersistedMergedRows(), 'restored'),
    );
    // A save resolves after its detail requests, so it must dedup against the merged rows as they are
    // then, not as they were when Save was clicked. Every change goes through commitMergedRows, which
    // keeps this ref equal to the latest list.
    const mergedRowsRef = useRef(mergedRows);
    const commitMergedRows = useCallback((update: (current: ProjectGridItem[]) => ProjectGridItem[]) => {
        const next = update(mergedRowsRef.current);
        mergedRowsRef.current = next;
        setMergedRows(next);
    }, []);
    const [mergedRowsUndo, setMergedRowsUndo] = useState<ProjectGridItem[] | null>(null);
    // The rows the latest save added, so the merged table can show and highlight them.
    const [recentlyAdded, setRecentlyAdded] = useState<{keys: ReadonlySet<string>; token: number} | null>(null);
    const [builderMessage, setBuilderMessage] = useState('');
    const [isAISearchLoginDialogOpen, setIsAISearchLoginDialogOpen] = useState(false);
    const tableSequence = useRef(1);
    const mergeSequence = useRef(0);
    const draftAccountSequence = useRef(0);
    const pendingRefreshTableId = useRef<string | null>(null);
    const lastSeenRows = useRef(rows);
    // Saves still loading project details. Sharing waits for them, or the share would leave out their rows.
    const [savesInFlight, setSavesInFlight] = useState(0);
    const saveControllers = useRef(new Set<AbortController>());
    // How many rows each search table has checked, to point out selections another table left unsaved.
    const selectionCounts = useRef(new Map<string, {count: number; title: string}>());
    // The search table a save is committing from, and where it sat on screen just before.
    const pendingScrollAnchor = useRef<{element: Element; top: number} | null>(null);

    const hasAISearchTable = searchTables.some((table) => table.type === 'ai');
    const standardSearchTableIds = searchTables.filter((table) => table.type === 'standard').map((table) => table.id);
    const standardSearchTableCount = standardSearchTableIds.length;

    // Mirror the merged results into sessionStorage on every change so however the visitor leaves
    // (the login reload, a manual refresh, SPA navigation), the draft can be restored on return.
    useEffect(() => {
        writePersistedMergedRows(mergedRows.map(stripProjectGridItem));
    }, [mergedRows]);

    // Leaving the page cancels the detail requests of saves still in flight.
    useEffect(() => {
        const controllers = saveControllers.current;
        return () => {
            controllers.forEach((controller) => controller.abort());
            controllers.clear();
        };
    }, []);

    // Keep the table that was saved from where it was on screen. The saved results card mounts (or grows)
    // above it, and the browser's scroll anchoring only compensates when its anchor sits below that change.
    // Reading the position forces layout, so any correction the browser made is already applied and only
    // what is left is scrolled away.
    useLayoutEffect(() => {
        const anchor = pendingScrollAnchor.current;
        pendingScrollAnchor.current = null;
        if (!anchor?.element.isConnected) {
            return;
        }
        const shift = anchor.element.getBoundingClientRect().top - anchor.top;
        if (Math.abs(shift) > 1) {
            window.scrollBy(0, shift);
        }
    }, [mergedRows]);

    // Revalidation is not a logout. Keep the draft while identity is being checked, and clear it
    // only when a known member actually logs out or changes accounts. Guest drafts survive login.
    const draftMemberRef = useRef(memberId);
    useEffect(() => {
        if (isInitializing || unverified) return;
        if (draftMemberRef.current && draftMemberRef.current !== memberId) {
            draftAccountSequence.current += 1;
            clearPersistedMergedRows();
            commitMergedRows(() => []);
            setMergedRowsUndo(null);
            setRecentlyAdded(null);
        }
        draftMemberRef.current = memberId;
    }, [commitMergedRows, isInitializing, unverified, memberId]);

    // Wrap the parent's share creator so a *successful* share drops the persisted draft — the share
    // now owns this snapshot, and returning to the builder should start clean. A failed attempt keeps
    // the draft so the user does not lose their merged rows.
    const handleCreateShare = useCallback(
        async (shareRows: ProjectGridRow[], name: string, note: string) => {
            const result = await onCreateShare(shareRows, name, note);
            clearPersistedMergedRows();
            return result;
        },
        [onCreateShare],
    );

    const handleAddSearchTable = () => {
        tableSequence.current += 1;
        const id = `search-table-${tableSequence.current}`;
        setSearchTables((current) => [...current, {id, type: 'standard'}]);
        setBuilderMessage('');
    };

    const handleAddAISearchTable = () => {
        if (!isAuthenticated) {
            setIsAISearchLoginDialogOpen(true);
            return;
        }

        if (hasAISearchTable) {
            return;
        }

        tableSequence.current += 1;
        const id = `search-table-${tableSequence.current}`;
        setSearchTables((current) => [
            ...current,
            {
                id,
                initialRows: [],
                rowsResetKey: 0,
                title: 'AI Search Table',
                type: 'ai',
            },
        ]);
        setBuilderMessage('');
    };

    const updateSearchTable = (tableId: string, update: (table: SearchTableState) => SearchTableState) => {
        setSearchTables((current) => current.map((table) => (table.id === tableId ? update(table) : table)));
    };

    const handleAISearch = async (tableId: string, query: string) => {
        if (!isAuthenticated) {
            return;
        }

        updateSearchTable(tableId, (table) => ({
            ...table,
            isLoading: true,
            message: 'Searching past projects with AI...',
            messageTone: 'loading',
        }));
        try {
            const response = await searchPastProjectsWithAI(query, AI_SEARCH_LIMIT);
            if (!response.available) {
                updateSearchTable(tableId, (table) => ({
                    ...table,
                    isLoading: false,
                    message: response.message || 'AI search is unavailable right now.',
                    messageTone: 'error',
                }));
                return;
            }

            const aiRows = response.results.map(toProjectGridRow);
            if (!aiRows.length) {
                updateSearchTable(tableId, (table) => ({
                    ...table,
                    isLoading: false,
                    message: 'AI search did not find matching past projects.',
                    messageTone: 'error',
                }));
                return;
            }

            updateSearchTable(tableId, (table) => ({
                ...table,
                initialRows: aiRows,
                isLoading: false,
                message: `${aiRows.length} AI result${aiRows.length === 1 ? '' : 's'} loaded into this table.`,
                messageTone: 'success',
                rowsResetKey: (table.rowsResetKey ?? 0) + 1,
                title: createAISearchTableTitle(response.query || query),
            }));
            setBuilderMessage('');
        } catch (err) {
            updateSearchTable(tableId, (table) => ({
                ...table,
                isLoading: false,
                message: getAISearchErrorMessage(err),
                messageTone: 'error',
            }));
        }
    };

    const handleRemoveSearchTable = (tableId: string) => {
        setSearchTables((current) => current.filter((table) => table.id !== tableId));
    };

    // Refresh is per-table: the refetch keeps serving stale rows (so the stack stays mounted and
    // every other table keeps its local curation), and once the fresh archive lands as a new `rows`
    // array, only the table that asked is remounted — via its key — with the new data.
    useEffect(() => {
        if (rows === lastSeenRows.current) {
            return;
        }
        lastSeenRows.current = rows;
        const tableId = pendingRefreshTableId.current;
        if (!tableId) {
            return;
        }
        pendingRefreshTableId.current = null;
        setSearchTables((current) =>
            current.map((table) =>
                table.id === tableId ? {...table, rowsResetKey: (table.rowsResetKey ?? 0) + 1} : table,
            ),
        );
        setBuilderMessage('Search table refreshed from the latest past-project archive.');
    }, [rows]);

    const handleRefreshSearchTable = useCallback(
        (tableId: string) => {
            pendingRefreshTableId.current = tableId;
            onRefreshRows?.();
            setBuilderMessage('Refreshing this search table from the latest past-project archive...');
        },
        [onRefreshRows],
    );

    const handleSelectionCountChange = useCallback((tableId: string, count: number, title: string) => {
        if (count) {
            selectionCounts.current.set(tableId, {count, title});
        } else {
            selectionCounts.current.delete(tableId);
        }
    }, []);

    // Save = merge a single search table's checked rows into the saved results. Projects already saved
    // (by id or content fingerprint) are skipped so each is stored once. The outcome goes back to the
    // table that saved, which shows it beside its Save button.
    const mergeLoadedRows = useCallback(
        (
            loadedRows: ProjectGridRow[],
            {failed, unavailable}: {failed: number[]; unavailable: number[]},
            accountSequence: number,
            tableId: string,
        ): SearchTableSaveResult => {
            setBuilderMessage('');
            if (accountSequence !== draftAccountSequence.current) {
                return {
                    tone: 'error',
                    message: 'Your sign-in changed while saving, so nothing was saved. Your selection is kept.',
                    retainedIndexes: loadedRows.map((_, index) => index),
                };
            }

            // Dedup against the merged rows as committed now, not as they were when Save was clicked:
            // another save, Reset or Remove may have landed meanwhile.
            const skipped = new Set([...failed, ...unavailable]);
            const savedFingerprints = new Set(
                mergedRowsRef.current.map((row) => createProjectGridFingerprint(stripProjectGridItem(row))),
            );
            const savedIds = new Set(mergedRowsRef.current.flatMap((row) => (row.id ? [row.id] : [])));
            const rowsToAppend: ProjectGridRow[] = [];
            let alreadySaved = 0;
            loadedRows.forEach((row, index) => {
                if (skipped.has(index)) {
                    return;
                }
                const fingerprint = createProjectGridFingerprint(row);
                if (savedFingerprints.has(fingerprint) || (row.id && savedIds.has(row.id))) {
                    alreadySaved += 1;
                    return;
                }
                savedFingerprints.add(fingerprint);
                if (row.id) savedIds.add(row.id);
                rowsToAppend.push(row);
            });

            if (rowsToAppend.length) {
                mergeSequence.current += 1;
                const added = createProjectGridItems(rowsToAppend, `merged-${mergeSequence.current}`);
                const anchor = document.querySelector(`[data-search-table-id="${tableId}"]`);
                pendingScrollAnchor.current = anchor ? {element: anchor, top: anchor.getBoundingClientRect().top} : null;
                commitMergedRows((current) => [...current, ...added]);
                setMergedRowsUndo((snapshot) => (snapshot ? appendUnsaved(snapshot, added) : null));
                setRecentlyAdded({keys: new Set(added.map((row) => row.__key)), token: mergeSequence.current});
            }

            const {tone, message} = describeSaveResult({
                added: rowsToAppend.length,
                alreadySaved,
                failed: failed.length,
                unavailable: unavailable.length,
                total: mergedRowsRef.current.length,
            });
            const unsavedElsewhere = describeUnsavedSelections(
                [...selectionCounts.current].filter(([id]) => id !== tableId).map(([, table]) => table),
            );
            return {
                tone,
                message: tone !== 'error' && unsavedElsewhere ? `${message} ${unsavedElsewhere}` : message,
                retainedIndexes: failed,
            };
        },
        [commitMergedRows],
    );

    const handleMergeSelectedFromTable = useCallback(
        (
            selected: ProjectGridRow[],
            {tableId, reportProgress}: SearchTableSaveHelpers,
        ): SearchTableSaveResult | Promise<SearchTableSaveResult> => {
            const accountSequence = draftAccountSequence.current;
            const savedIds = new Set(mergedRowsRef.current.flatMap((row) => (row.id ? [row.id] : [])));
            // Only compact archive rows not saved yet need a detail request. Complete rows (AI results,
            // restored drafts) and already-saved projects are handled within the click.
            const loadIndexes = selected.flatMap((row, index) =>
                needsProjectGridHydration(row) && !savedIds.has(row.id as string) ? [index] : [],
            );
            if (!loadIndexes.length) {
                return mergeLoadedRows(selected, {failed: [], unavailable: []}, accountSequence, tableId);
            }

            const controller = new AbortController();
            saveControllers.current.add(controller);
            setSavesInFlight((count) => count + 1);
            return hydrateProjectGridRowsSettled(
                loadIndexes.map((index) => selected[index]),
                {signal: controller.signal, onProgress: reportProgress},
            )
                .then(({rows: loadedRows, failedIndexes, unavailableIndexes}) => {
                    const rowsWithDetails = [...selected];
                    loadIndexes.forEach((selectedIndex, loadedIndex) => {
                        rowsWithDetails[selectedIndex] = loadedRows[loadedIndex];
                    });
                    return mergeLoadedRows(
                        rowsWithDetails,
                        {
                            failed: failedIndexes.map((loadedIndex) => loadIndexes[loadedIndex]),
                            unavailable: unavailableIndexes.map((loadedIndex) => loadIndexes[loadedIndex]),
                        },
                        accountSequence,
                        tableId,
                    );
                })
                .finally(() => {
                    saveControllers.current.delete(controller);
                    setSavesInFlight((count) => count - 1);
                });
        },
        [mergeLoadedRows],
    );

    // Lets a search table mark the projects that are already saved.
    const savedIdentity = useMemo(
        () => ({
            ids: new Set(mergedRows.flatMap((row) => (row.id ? [row.id] : []))),
            fingerprints: new Set(mergedRows.map((row) => createProjectGridFingerprint(stripProjectGridItem(row)))),
        }),
        [mergedRows],
    );
    const isRowSaved = useCallback(
        (row: ProjectGridRow) =>
            (Boolean(row.id) && savedIdentity.ids.has(row.id as string)) ||
            savedIdentity.fingerprints.has(createProjectGridFingerprint(row)),
        [savedIdentity],
    );

    const handleViewMergedResults = useCallback(() => {
        const section = document.getElementById(MERGED_RESULTS_ID);
        if (!section) {
            return;
        }
        const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
        section.scrollIntoView?.({behavior: reduceMotion ? 'auto' : 'smooth', block: 'start'});
        // Move keyboard focus along with the view.
        section.querySelector<HTMLElement>('.project-grid-card-title')?.focus({preventScroll: true});
    }, []);

    const handleDeleteMergedRow = (row: ProjectGridItem) => {
        setMergedRowsUndo(mergedRowsRef.current);
        commitMergedRows((current) => current.filter((item) => item.__key !== row.__key));
        setBuilderMessage('Project removed from merged results.');
    };

    const handleDeleteMergedRows = (rowsToRemove: ProjectGridItem[]) => {
        if (!rowsToRemove.length) {
            return;
        }
        const removeKeys = new Set(rowsToRemove.map((row) => row.__key));
        setMergedRowsUndo(mergedRowsRef.current);
        commitMergedRows((current) => current.filter((item) => !removeKeys.has(item.__key)));
        setBuilderMessage(
            `${rowsToRemove.length} project${rowsToRemove.length === 1 ? '' : 's'} removed from merged results.`,
        );
    };

    const handleUndoMergedRows = () => {
        if (!mergedRowsUndo) {
            return;
        }

        commitMergedRows(() => mergedRowsUndo);
        setMergedRowsUndo(null);
        setBuilderMessage('Merged results restored.');
    };

    const handleResetMergedRows = () => {
        if (!mergedRowsRef.current.length) {
            return;
        }

        setMergedRowsUndo(mergedRowsRef.current);
        commitMergedRows(() => []);
        setBuilderMessage('Merged results reset. Undo Merged Change can restore them until you leave this page.');
    };

    return (
        <div className="past-projects-builder">
            {mergedRows.length > 0 || mergedRowsUndo ? (
                <MergedResultsTable
                    id={MERGED_RESULTS_ID}
                    className="past-projects-saved-results"
                    rows={mergedRows}
                    recentlyAdded={recentlyAdded}
                    pendingSaveCount={savesInFlight}
                    onCreateShare={handleCreateShare}
                    onDeleteRow={handleDeleteMergedRow}
                    onDeleteRows={handleDeleteMergedRows}
                    canUndoRows={Boolean(mergedRowsUndo)}
                    onUndoRows={handleUndoMergedRows}
                    onResetRows={handleResetMergedRows}
                />
            ) : null}

            <PastProjectsActionBar
                builderMessage={builderMessage}
                error={error}
                loading={loading}
                aiSearchDisabled={hasAISearchTable}
                aiSearchLoginRequired={!isAuthenticated}
                onAddAISearchTable={handleAddAISearchTable}
                onAddSearchTable={handleAddSearchTable}
            />

            {isAISearchLoginDialogOpen ? (
                <PastProjectsDialog
                    title="Sign in required"
                    cancelLabel="Close"
                    confirmLabel="Sign In"
                    onCancel={() => setIsAISearchLoginDialogOpen(false)}
                    onConfirm={() => {
                        window.location.href = buildLoginPath(`${window.location.pathname}${window.location.search}`);
                    }}
                >
                    <p>You need to sign in before using AI search.</p>
                </PastProjectsDialog>
            ) : null}

            {loading ? <div className="project-grid-card">
                <div className="project-grid-state">Loading past projects...</div>
            </div> : null}
            {error ? <div className="project-grid-card">
                <div className="project-grid-state project-grid-state-error">{error}</div>
            </div> : null}

            {!loading && !error ? (
                <div className="search-table-stack">
                    {searchTables.map((table) => {
                        const isAISearchTable = table.type === 'ai';
                        const title =
                            table.title ??
                            (isAISearchTable
                                ? 'AI Search Table'
                                : standardSearchTableCount === 1
                                    ? 'Search Table'
                                    : `Search Table ${standardSearchTableIds.indexOf(table.id) + 1}`);

                        return (
                            <SearchTableCard
                                key={table.rowsResetKey === undefined ? table.id : `${table.id}-${table.rowsResetKey}`}
                                canRemove={searchTables.length > 1}
                                description={
                                    isAISearchTable
                                        ? 'Use AI to load matching past projects into this table, then check the projects you want and click Save Selected.'
                                        : undefined
                                }
                                emptyMessage={
                                    isAISearchTable
                                        ? 'Run AI search to load projects into this table.'
                                        : undefined
                                }
                                initialRows={table.initialRows ?? rows}
                                controlsStatus={
                                    table.message && table.messageTone && table.messageTone !== 'loading' ? (
                                        <PastProjectsAIStatus message={table.message} tone={table.messageTone}/>
                                    ) : undefined
                                }
                                searchControl={
                                    isAISearchTable ? (
                                        <PastProjectsAISearchForm
                                            isAuthenticated={isAuthenticated}
                                            loading={Boolean(table.isLoading)}
                                            onSearch={(query) => handleAISearch(table.id, query)}
                                        />
                                    ) : undefined
                                }
                                tableId={table.id}
                                title={title}
                                className={
                                    isAISearchTable
                                        ? `is-ai-search-table${table.rowsResetKey ? ' has-ai-results' : ''}`
                                        : undefined
                                }
                                resultsMotionKey={isAISearchTable ? table.rowsResetKey : undefined}
                                onRemove={handleRemoveSearchTable}
                                onRefresh={isAISearchTable || !onRefreshRows ? undefined : handleRefreshSearchTable}
                                isRowSaved={isRowSaved}
                                onViewMergedResults={handleViewMergedResults}
                                onSelectionCountChange={handleSelectionCountChange}
                                onMergeSelected={handleMergeSelectedFromTable}
                            />
                        );
                    })}

                    {!searchTables.length ? (
                        <div className="project-grid-card project-grid-empty-shell">
                            <div className="project-grid-empty">
                                No search tables are open. Add a new table to start filtering past projects.
                            </div>
                        </div>
                    ) : null}
                </div>
            ) : null}
        </div>
    );
};
