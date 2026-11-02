// The `@/features/projects` stand-in for the PastProjectsPage tests: each component is a button
// (or a heading) that calls the page's callback with a fixed change, so the tests drive the page's
// share flow without rendering the real builder or tables. The builder and the add-more search say
// which list they were given (`data-rows`) and which catalog is in context (`data-catalog`).
import type {ProjectGridRow} from '@/features/projects/api';
import {useProjectCatalog} from '@/features/projects/catalog/projectCatalog';

const rowTitles = (rows: ProjectGridRow[] = []) => rows.map((row) => row.project_title).join('|');

export const pastProjectsModuleStub = (sampleRow: ProjectGridRow, addedRow: ProjectGridRow) => ({
    createProjectGridItems: (rows: ProjectGridRow[]) =>
        rows.map((row, index) => ({...row, __key: `row-${index}`})),
    MergedResultsTable: ({
                             note,
                             onUpdateShare,
                             rows,
                             sharedAt,
                             title,
                         }: {
        note?: string;
        sharedAt?: string;
        onUpdateShare?: (
            rows: ProjectGridRow[],
            name: string,
            note: string,
        ) => Promise<void>;
        rows: Array<ProjectGridRow & { __key: string }>;
        title: string;
    }) => {
        const cleanRows = rows.map(({__key, ...row}) => {
            void __key;
            return row;
        });
        return (
            <div>
                <h2 data-testid="share-title" data-shared-at={sharedAt}>{title}</h2>
                <div data-testid="share-note">{note}</div>
                <button
                    type="button"
                    onClick={() =>
                        void onUpdateShare?.(
                            cleanRows,
                            title,
                            'Updated note',
                        ).catch(() => undefined)
                    }
                >
                    Update mocked note
                </button>
                <button
                    type="button"
                    onClick={() =>
                        void onUpdateShare?.(
                            cleanRows.map((row, index) =>
                                index === 0
                                    ? {...row, team_name: 'Edited Team Alpha'}
                                    : row,
                            ),
                            title,
                            note ?? '',
                        ).catch(() => undefined)
                    }
                >
                    Edit mocked row
                </button>
                <button
                    type="button"
                    onClick={() =>
                        void onUpdateShare?.(
                            cleanRows.slice(1),
                            title,
                            note ?? '',
                        ).catch(() => undefined)
                    }
                >
                    Delete first mocked row
                </button>
                <button
                    type="button"
                    onClick={() =>
                        void onUpdateShare?.(
                            cleanRows,
                            'Renamed share',
                            note ?? '',
                        ).catch(() => undefined)
                    }
                >
                    Rename mocked share
                </button>
                <button
                    type="button"
                    onClick={() =>
                        void onUpdateShare?.(cleanRows, '', note ?? '').catch(() => undefined)
                    }
                >
                    Clear mocked name
                </button>
                <button
                    type="button"
                    onClick={() =>
                        void onUpdateShare?.(
                            cleanRows,
                            title,
                            note ?? '',
                        ).catch(() => undefined)
                    }
                >
                    No-op update
                </button>
                <button
                    type="button"
                    onClick={() =>
                        void onUpdateShare?.(
                            [...cleanRows, addedRow],
                            title,
                            note ?? '',
                        ).catch(() => undefined)
                    }
                >
                    Edit with added row
                </button>
                <button
                    type="button"
                    onClick={() =>
                        void onUpdateShare?.(
                            [...cleanRows].reverse(),
                            title,
                            note ?? '',
                        ).catch(() => undefined)
                    }
                >
                    Reverse mocked rows
                </button>
            </div>
        );
    },
    MyCurationsPanel: () => <section aria-label="My Curations (mocked)"/>,
    SharedPastProjectMergeSearch: function SharedPastProjectMergeSearch({
                                       onAddRows,
                                       rows,
                                   }: {
        onAddRows: (rows: ProjectGridRow[]) => Promise<void>;
        rows?: ProjectGridRow[];
    }) {
        const {key} = useProjectCatalog();
        return (
            <button
                type="button"
                data-catalog={key}
                data-rows={rowTitles(rows)}
                onClick={() => void onAddRows([addedRow]).catch(() => undefined)}
            >
                Add mocked row
            </button>
        );
    },
    PastProjectsBuilder: function PastProjectsBuilder({
                              initialSearch,
                              onCreateShare,
                              rows,
                          }: {
        initialSearch?: string;
        onCreateShare: (
            rows: ProjectGridRow[],
            name: string,
            note: string,
        ) => Promise<unknown>;
        rows?: ProjectGridRow[];
    }) {
        const {key} = useProjectCatalog();
        return (
            <button
                type="button"
                data-initial-search={initialSearch}
                data-catalog={key}
                data-rows={rowTitles(rows)}
                onClick={() =>
                    void onCreateShare(
                        [sampleRow],
                        'Spring finalists',
                        'Review note',
                    )
                }
            >
                Create mocked share
            </button>
        );
    },
});
