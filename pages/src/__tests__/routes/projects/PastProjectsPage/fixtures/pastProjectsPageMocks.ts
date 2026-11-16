// vi.mock factories shared by the test files below this directory; each file's vi.mock calls them.
import {vi} from 'vitest';
import {addedRow, allGridState, authState, gridState, mockNavigate, mockRetryShare, sampleRow, sharedState} from '@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsPageState';

type ImportOriginal = <T = unknown>() => Promise<T>;

export const authModule = async (importOriginal: ImportOriginal) => {
    const actual = await importOriginal<typeof import('@/features/auth')>();
    return {...actual, useAuth: () => ({...actual.useAuth(), user: authState.user})};
};

export const reactRouterModule = async (importOriginal: ImportOriginal) => {
    const actual = await importOriginal<typeof import('react-router')>();
    return {
        ...actual,
        useNavigate: () => mockNavigate,
        useParams: () => {
            const current = sharedState.share as { id?: unknown } | null;
            return {
                shareId: sharedState.shareError
                    ? 'missing-share'
                    : typeof current?.id === 'string' ? current.id : undefined,
            };
        },
    };
};

export const projectsApiModule = () => ({
    DEFAULT_PAST_PROJECT_SHARE_NAME: 'Past Project Curation',
    createPastProjectShare: vi.fn(),
    fetchPastProjectShare: vi.fn(),
    updatePastProjectShare: vi.fn(),
});

export const useProjectGridDataModule = () => ({
    usePastProjectGridData: (enabled = true) => {
        gridState.enabled.push(enabled);
        return {error: null, loading: gridState.loading, rows: gridState.rows, refetch: vi.fn()};
    },
    useAllProjectGridData: (enabled = true) => {
        allGridState.enabled.push(enabled);
        return {error: null, loading: false, rows: allGridState.rows, refetch: vi.fn()};
    },
    usePastProjectShareData: () => ({
        error: sharedState.shareError,
        loading: false,
        share: sharedState.share,
        notFound: sharedState.shareNotFound,
        retry: mockRetryShare,
    }),
});

export const projectsModule = async () =>
    (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsModuleStub')).pastProjectsModuleStub(
        sampleRow,
        addedRow,
    );

export const pastProjectsBuilderModule = async () => ({
    PastProjectsBuilder: (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsModuleStub'))
        .pastProjectsModuleStub(sampleRow, addedRow).PastProjectsBuilder,
});

export const myCurationsPanelModule = async () => ({
    MyCurationsPanel: (await import('@/__tests__/routes/projects/PastProjectsPage/fixtures/pastProjectsModuleStub'))
        .pastProjectsModuleStub(sampleRow, addedRow).MyCurationsPanel,
});

export const sharedEditsUseProjectGridDataModule = () => ({
    usePastProjectGridData: () => ({
        error: null,
        loading: false,
        rows: [sampleRow],
        refetch: vi.fn(),
    }),
    // The owner's add-more search lists every project.
    useAllProjectGridData: () => ({
        error: null,
        loading: false,
        rows: [sampleRow],
        refetch: vi.fn(),
    }),
    usePastProjectShareData: () => ({
        error: sharedState.shareError,
        loading: false,
        share: sharedState.share,
        notFound: sharedState.shareNotFound,
        retry: mockRetryShare,
    }),
});
