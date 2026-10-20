import {useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState} from 'react';
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
    createProjectGridItems,
    createProjectGridRowMatcher,
    stripProjectGridItem,
    type ProjectGridItem,
    type ProjectGridRow,
} from './projectGrid';
import {describeSaveResult, pluralize} from './saveResults';

const INITIAL_SEARCH_TABLE: SearchTableState = {id: 'search-table-1', type: 'standard'};

const AI_SEARCH_LIMIT = 10;

// The curation being built (its saved projects, name and note) is a draft until it is saved, which needs signing
// in — and the login button reloads the page. Keep the draft in localStorage so it survives that reload, closing
// the tab and coming back later; it is dropped once it is saved. The draft records whose it is: a member's draft is
// only restored for that member, so the next person on a shared computer does not get it, while a guest's draft
// carries over when the guest signs in.
const DRAFT_STORAGE_KEY = 'past-projects:builder:draft';
// Before drafts outlived the tab, the projects alone were kept in sessionStorage. Picked up once; the first write
// of the new draft removes it.
const LEGACY_MERGED_ROWS_STORAGE_KEY = 'past-projects:builder:merged-rows';

interface CurationDraft {
    owner: string | null;
    rows: ProjectGridRow[];
    name: string;
    note: string;
}

const EMPTY_DRAFT: CurationDraft = {owner: null, rows: [], name: '', note: ''};

const readLegacyDraft = (): CurationDraft => {
    try {
        const raw = sessionStorage.getItem(LEGACY_MERGED_ROWS_STORAGE_KEY);
        const rows = raw ? JSON.parse(raw) : [];
        return Array.isArray(rows) ? {...EMPTY_DRAFT, rows: rows as ProjectGridRow[]} : EMPTY_DRAFT;
    } catch {
        return EMPTY_DRAFT;
    }
};

const readPersistedDraft = (memberId: string | null): CurationDraft => {
    try {
        const raw = localStorage.getItem(DRAFT_STORAGE_KEY);
        if (!raw) return readLegacyDraft();
        const parsed = JSON.parse(raw) as Partial<CurationDraft> | null;
        const owner = typeof parsed?.owner === 'string' ? parsed.owner : null;
        if (!parsed || !Array.isArray(parsed.rows) || (owner && owner !== memberId)) {
            return EMPTY_DRAFT;
        }
        return {
            owner,
            rows: parsed.rows,
            name: typeof parsed.name === 'string' ? parsed.name : '',
            note: typeof parsed.note === 'string' ? parsed.note : '',
        };
    } catch {
        return EMPTY_DRAFT;
    }
};

const writePersistedDraft = (draft: CurationDraft) => {
    try {
        sessionStorage.removeItem(LEGACY_MERGED_ROWS_STORAGE_KEY);
        if (draft.rows.length) {
            localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
        } else {
            localStorage.removeItem(DRAFT_STORAGE_KEY);
        }
    } catch {
        // localStorage can throw (private mode / quota / disabled) — degrade to in-memory only.
    }
};

const clearPersistedDraft = () => {
    try {
        localStorage.removeItem(DRAFT_STORAGE_KEY);
    } catch {
        // ignore — nothing to clean up if storage is unavailable.
    }
};

const MERGED_RESULTS_ID = 'past-projects-saved-results';

// Each table saves only its own checked rows; say so when other tables still hold checked rows that are not saved.
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
    const inSnapshot = createProjectGridRowMatcher(snapshot);
    return [...snapshot, ...added.filter((row) => !inSnapshot.has(row))];
};

// What to keep in place while the saved results change: when the user is working in the saved results
// (naming the list, writing the note, checking rows), the element they are in, since the save can add a row
// above it; otherwise the search table holding focus, else the one that saved. Only while it is on screen:
// off-screen, the browser's own scroll anchoring keeps what they are looking at where it is.
const findScrollAnchor = (tableId: string) => {
    const active = document.activeElement;
    if (active?.closest(`#${MERGED_RESULTS_ID}`)) {
        const {top, bottom} = active.getBoundingClientRect();
        return bottom > 0 && top < window.innerHeight ? {element: active, top} : null;
    }
    const candidates = [
        active?.closest('[data-search-table-id]'),
        document.querySelector(`[data-search-table-id="${tableId}"]`),
    ];
    for (const element of candidates) {
        if (element) {
            const {top, bottom} = element.getBoundingClientRect();
            if (bottom > 0 && top < window.innerHeight) {
                return {element, top};
            }
        }
    }
    return null;
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
    /** Seeds the first search table's search (e.g. from "Search Past Projects for …" on Current Projects). */
    initialSearch?: string;
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
                                        initialSearch = '',
                                        onRefreshRows,
                                        onCreateShare,
                                    }: PastProjectsBuilderProps) => {
    const {isAuthenticated, isInitializing, unverified, user} = useAuth();
    const memberId = user?.member_uuid ?? null;
    const [searchTables, setSearchTables] = useState<SearchTableState[]>(() => [INITIAL_SEARCH_TABLE]);
    // Seed from the draft kept from an earlier visit (or the login reload).
    const [restoredDraft] = useState(() => readPersistedDraft(memberId));
    const [mergedRows, setMergedRows] = useState<ProjectGridItem[]>(() =>
        createProjectGridItems(restoredDraft.rows, 'restored'),
    );
    const [nameDraft, setNameDraft] = useState(restoredDraft.name);
    const [noteDraft, setNoteDraft] = useState(restoredDraft.note);
    // The member the draft belongs to (null for a guest's).
    const draftMemberRef = useRef(memberId);
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
    // While a shareable link is being created, saving waits: the link is made from the rows shown at the click,
    // and the draft is dropped once it exists, so rows saved meanwhile would be lost.
    const [isCreatingShare, setIsCreatingShare] = useState(false);
    // The rows each search table has checked but not submitted, to point out selections another table left
    // unsaved.
    const pendingSelections = useRef(new Map<string, {rows: ProjectGridRow[]; title: string}>());
    // The search table to keep in place when a save commits, and where it sat on screen just before.
    const pendingScrollAnchor = useRef<{element: Element; top: number} | null>(null);

    const searchTablesHeadingId = useId();
    const hasAISearchTable = searchTables.some((table) => table.type === 'ai');
    const standardSearchTableIds = searchTables.filter((table) => table.type === 'standard').map((table) => table.id);
    const standardSearchTableCount = standardSearchTableIds.length;

    // Mirror the draft into localStorage on every change so however the visitor leaves (the login reload, a
    // refresh, closing the tab, SPA navigation), it can be restored on return.
    useEffect(() => {
        writePersistedDraft({
            owner: draftMemberRef.current,
            rows: mergedRows.map(stripProjectGridItem),
            name: nameDraft,
            note: noteDraft,
        });
    }, [mergedRows, nameDraft, noteDraft]);

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
    useEffect(() => {
        if (isInitializing || unverified) return;
        if (draftMemberRef.current && draftMemberRef.current !== memberId) {
            draftAccountSequence.current += 1;
            clearPersistedDraft();
            commitMergedRows(() => []);
            setMergedRowsUndo(null);
            setRecentlyAdded(null);
            setNameDraft('');
            setNoteDraft('');
        }
        draftMemberRef.current = memberId;
    }, [commitMergedRows, isInitializing, unverified, memberId]);

    // Wrap the parent's share creator so a *successful* share drops the persisted draft — the share
    // now owns this snapshot, and returning to the builder should start clean. A failed attempt keeps
    // the draft so the user does not lose their merged rows.
    const handleCreateShare = useCallback(
        async (shareRows: ProjectGridRow[], name: string, note: string) => {
            setIsCreatingShare(true);
            try {
                const result = await onCreateShare(shareRows, name, note);
                clearPersistedDraft();
                return result;
            } finally {
                setIsCreatingShare(false);
            }
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
    // array, only the table that asked is reset — via its resetKey — with the new data. The card stays
    // mounted, so a save it has running still reports its outcome there.
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

    const handleSelectionChange = useCallback((tableId: string, selectedRows: ProjectGridRow[], title: string) => {
        if (selectedRows.length) {
            pendingSelections.current.set(tableId, {rows: selectedRows, title});
        } else {
            pendingSelections.current.delete(tableId);
        }
    }, []);

    // Save = merge a single search table's checked rows into the saved results. Projects already saved
    // (by id or content fingerprint) are skipped so each is stored once. The outcome goes back to the
    // table that saved, which shows it beside its Save button.
    const mergeLoadedRows = useCallback(
        (
            loadedRows: ProjectGridRow[],
            {failed, unavailable, presaved}: {failed: number[]; unavailable: number[]; presaved: number[]},
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
            // another save, Reset or Remove may have landed meanwhile. Rows that were already saved at the
            // click were not loaded, so they are never appended. One removed from the saved results meanwhile
            // stays removed, rather than a copy without abstract or students taking its place, and stays
            // checked so it can be saved again.
            const saved = createProjectGridRowMatcher(mergedRowsRef.current);
            const removedMeanwhile = presaved.filter((index) => !saved.has(loadedRows[index]));
            const skipped = new Set([...failed, ...unavailable, ...presaved]);
            const rowsToAppend: ProjectGridRow[] = [];
            let alreadySaved = presaved.length - removedMeanwhile.length;
            loadedRows.forEach((row, index) => {
                if (skipped.has(index)) {
                    return;
                }
                if (saved.has(row)) {
                    alreadySaved += 1;
                    return;
                }
                saved.add(row);
                rowsToAppend.push(row);
            });

            if (rowsToAppend.length) {
                mergeSequence.current += 1;
                const added = createProjectGridItems(rowsToAppend, `merged-${mergeSequence.current}`);
                pendingScrollAnchor.current = findScrollAnchor(tableId);
                commitMergedRows((current) => [...current, ...added]);
                setMergedRowsUndo((snapshot) => (snapshot ? appendUnsaved(snapshot, added) : null));
                setRecentlyAdded({keys: new Set(added.map((row) => row.__key)), token: mergeSequence.current});
            }

            const {tone, message} = describeSaveResult(
                {added: rowsToAppend.length, alreadySaved, failed: failed.length, unavailable: unavailable.length},
                {
                    added: `added to Saved Merged Results (${mergedRowsRef.current.length} in total).`,
                    already: 'saved',
                    place: 'in Saved Merged Results',
                    retryLabel: 'Save Selected',
                },
            );
            const removed = removedMeanwhile.length;
            const removedNote = removed
                ? `${pluralize(removed, 'project')} ${removed === 1 ? 'was' : 'were'} removed from Saved Merged ` +
                  `Results while saving and ${removed === 1 ? 'is' : 'are'} still selected.`
                : '';
            // Checked rows another table holds that are not saved now (this save may have saved some of them).
            const unsavedElsewhere = describeUnsavedSelections(
                [...pendingSelections.current].flatMap(([id, selection]) => {
                    const count = id === tableId ? 0 : selection.rows.filter((row) => !saved.has(row)).length;
                    return count ? [{count, title: selection.title}] : [];
                }),
            );
            return {
                tone,
                message: [message, removedNote, tone !== 'error' ? unsavedElsewhere : '']
                    .filter(Boolean)
                    .join(' '),
                retainedIndexes: [...failed, ...removedMeanwhile].sort((left, right) => left - right),
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
            const saved = createProjectGridRowMatcher(mergedRowsRef.current);
            const presaved = selected.flatMap((row, index) => (saved.has(row) ? [index] : []));
            // Only compact archive rows not saved yet need a detail request. Complete rows (AI results,
            // restored drafts) and already-saved projects are handled within the click.
            const loadIndexes = selected.flatMap((row, index) =>
                needsProjectGridHydration(row) && !saved.has(row) ? [index] : [],
            );
            if (!loadIndexes.length) {
                return mergeLoadedRows(selected, {failed: [], unavailable: [], presaved}, accountSequence, tableId);
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
                            presaved,
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
    const isRowSaved = useMemo(() => createProjectGridRowMatcher(mergedRows).has, [mergedRows]);

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
                    nameDraft={nameDraft}
                    noteDraft={noteDraft}
                    onNameDraftChange={setNameDraft}
                    onNoteDraftChange={setNoteDraft}
                    onDeleteRow={handleDeleteMergedRow}
                    onDeleteRows={handleDeleteMergedRows}
                    canUndoRows={Boolean(mergedRowsUndo)}
                    onUndoRows={handleUndoMergedRows}
                    onResetRows={handleResetMergedRows}
                />
            ) : null}

            <section className="past-projects-search-tables" aria-labelledby={searchTablesHeadingId}>
                <PastProjectsActionBar
                    headingId={searchTablesHeadingId}
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

                {loading ? <p className="project-grid-state">Loading past projects...</p> : null}
                {error ? (
                    <p className="project-grid-state project-grid-state-error itg-error" role="alert">
                        {error}
                    </p>
                ) : null}

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
                                    key={table.id}
                                    resetKey={table.rowsResetKey}
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
                                    initialSearch={table.id === INITIAL_SEARCH_TABLE.id ? initialSearch : undefined}
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
                                    mergeDisabled={isCreatingShare}
                                    isRowSaved={isRowSaved}
                                    onViewMergedResults={handleViewMergedResults}
                                    onSelectionChange={handleSelectionChange}
                                    onMergeSelected={handleMergeSelectedFromTable}
                                />
                            );
                        })}

                        {!searchTables.length ? (
                            <p className="project-grid-empty project-grid-empty-shell">
                                No search tables are open. Add a new table to start searching past projects.
                            </p>
                        ) : null}
                    </div>
                ) : null}
            </section>
        </div>
    );
};
