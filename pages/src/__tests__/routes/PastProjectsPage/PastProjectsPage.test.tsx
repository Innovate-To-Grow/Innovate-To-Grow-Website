import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {MemoryRouter} from 'react-router';

import {PastProjectsPage} from '@/routes/PastProjectsPage/PastProjectsPage';
import {
  createPastProjectShare,
  fetchPastProjectShare,
  updatePastProjectShare,
  type PastProjectShare,
} from '@/features/projects/api';

const {
    addedRow,
    mockNavigate,
    mockRetryShare,
    sampleRow,
    sharedState,
} = vi.hoisted(() => {
    const sample = {
        id: '11111111-1111-4111-8111-111111111111',
        semester_label: '2025 Spring',
        class_code: 'CAP',
        team_number: '101',
        team_name: 'Team Alpha',
        project_title: 'Shared Project',
        organization: 'Acme',
        industry: 'Technology',
        abstract: 'A detailed project abstract.',
        student_names: 'Alice, Bob',
        is_presenting: '',
    };
    return {
        sampleRow: sample,
        addedRow: {
            ...sample,
            id: '22222222-2222-4222-8222-222222222222',
            team_number: '202',
            team_name: 'Team Beta',
            project_title: 'Queued Project',
        },
        mockNavigate: vi.fn(),
        mockRetryShare: vi.fn(),
        sharedState: {share: null as unknown, shareError: null as string | null, shareNotFound: false},
    };
});

vi.mock('react-router', async (importOriginal) => {
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
});

vi.mock('@/features/projects/api', () => ({
    DEFAULT_PAST_PROJECT_SHARE_NAME: 'Past Project Curation',
    createPastProjectShare: vi.fn(),
    fetchPastProjectShare: vi.fn(),
    updatePastProjectShare: vi.fn(),
}));

vi.mock('@/features/projects/hooks/useProjectGridData', () => ({
    usePastProjectGridData: () => ({
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
}));

vi.mock('@/features/projects', async () =>
    (await import('@/__tests__/routes/PastProjectsPage/pastProjectsModuleStub')).pastProjectsModuleStub(
        sampleRow,
        addedRow,
    ),
);

const shareFixture = (
    overrides: Partial<PastProjectShare> = {},
): PastProjectShare => ({
    id: 'share-abc',
    name: 'Spring finalists',
    rows: [sampleRow],
    note: 'Original note',
    details_text: '<strong>Details</strong>',
    version: 4,
    share_url: '/past-projects/share-abc',
    can_edit: true,
    created_at: '2026-06-08T00:00:00Z',
    ...overrides,
});

const renderPage = () =>
    render(
        <MemoryRouter initialEntries={['/past-projects']}>
            <PastProjectsPage/>
        </MemoryRouter>,
    );

describe('PastProjectsPage', () => {
    beforeEach(() => {
        sharedState.share = null;
        sharedState.shareError = null;
        sharedState.shareNotFound = false;
        mockNavigate.mockReset();
        mockRetryShare.mockReset();
        vi.mocked(createPastProjectShare).mockReset();
        vi.mocked(fetchPastProjectShare).mockReset();
        vi.mocked(updatePastProjectShare).mockReset();
    });

    afterEach(() => {
        cleanup();
    });

    it('redirects to the shareable link route after creating a share', async () => {
        vi.mocked(createPastProjectShare).mockResolvedValue(
            shareFixture({
                version: 1,
                note: 'Review note',
            }),
        );

        renderPage();
        fireEvent.click(
            screen.getByRole('button', {name: 'Create mocked share'}),
        );

        await waitFor(() => {
            expect(createPastProjectShare).toHaveBeenCalledWith(
                [sampleRow],
                'Spring finalists',
                'Review note',
            );
            // The curation's page says it was saved.
            expect(mockNavigate).toHaveBeenCalledWith(
                '/past-projects/share-abc',
                {state: {curationSaved: true}},
            );
        });
    });

    it('renames a shared page', async () => {
        const initial = shareFixture();
        sharedState.share = initial;
        vi.mocked(updatePastProjectShare).mockResolvedValue(
            shareFixture({name: 'Renamed share', version: 5}),
        );

        renderPage();
        fireEvent.click(screen.getByRole('button', {name: 'Rename mocked share'}));

        await waitFor(() =>
            expect(updatePastProjectShare).toHaveBeenCalledWith(initial.id, {
                name: 'Renamed share',
                version: 4,
            }),
        );
    });

    it('titles a share stored without a name with the default curation title', async () => {
        sharedState.share = shareFixture({name: '  '});

        renderPage();

        expect(await screen.findByTestId('share-title')).toHaveTextContent('Past Project Curation');
    });

    it('heads the builder with the archive size, the years it spans and a lede', () => {
        renderPage();

        expect(screen.getByRole('heading', {level: 1, name: 'Past Projects'})).toBeInTheDocument();
        expect(screen.getByText('1 project since 2025')).toHaveClass('itg-page-meta');
        expect(screen.getByText(/^Search past Innovate to Grow projects, check the ones you want/)).toHaveClass('itg-lead');
    });

    it("lists the member's saved curations above the builder", () => {
        renderPage();

        const curations = screen.getByRole('region', {name: 'My Curations (mocked)'});
        const builder = screen.getByRole('button', {name: 'Create mocked share'});
        expect(curations.compareDocumentPosition(builder) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it('confirms a curation the owner just saved, and only then', () => {
        sharedState.share = shareFixture();
        const saved = render(
            <MemoryRouter initialEntries={[{pathname: '/past-projects/share-abc', state: {curationSaved: true}}]}>
                <PastProjectsPage/>
            </MemoryRouter>,
        );
        expect(screen.getByRole('status')).toHaveTextContent(
            'Curation saved. It is listed under My Curations on the Past Projects page, and you can keep editing it here.',
        );
        expect(screen.getByRole('link', {name: 'Past Projects'})).toHaveAttribute('href', '/past-projects');
        saved.unmount();

        // Opened from a link, or by someone who cannot edit it: no confirmation.
        const opened = render(
            <MemoryRouter initialEntries={['/past-projects/share-abc']}>
                <PastProjectsPage/>
            </MemoryRouter>,
        );
        expect(screen.queryByText(/Curation saved/)).toBeNull();
        opened.unmount();
        sharedState.share = shareFixture({can_edit: false});
        render(
            <MemoryRouter initialEntries={[{pathname: '/past-projects/share-abc', state: {curationSaved: true}}]}>
                <PastProjectsPage/>
            </MemoryRouter>,
        );
        expect(screen.queryByText(/Curation saved/)).toBeNull();
    });

    it('passes the ?value= search on to the builder', () => {
        render(
            <MemoryRouter initialEntries={['/past-projects?value=hydroponics']}>
                <PastProjectsPage/>
            </MemoryRouter>,
        );

        expect(screen.getByRole('button', {name: 'Create mocked share'})).toHaveAttribute(
            'data-initial-search',
            'hydroponics',
        );
    });

    it('shows a shared list with its date and a way to start a list of your own', async () => {
        sharedState.share = shareFixture();

        renderPage();

        expect(await screen.findByTestId('share-title')).toHaveAttribute('data-shared-at', '2026-06-08T00:00:00Z');
        expect(screen.queryByRole('heading', {level: 1, name: 'Past Projects'})).toBeNull();
        expect(screen.getByText(/Want to make your own list\?/)).toBeInTheDocument();
        expect(screen.getByRole('link', {name: 'Search all past projects'})).toHaveAttribute('href', '/past-projects');
    });

    it('explains a shared list that does not exist', () => {
        sharedState.shareError = 'Request failed with status code 404';
        sharedState.shareNotFound = true;

        renderPage();

        expect(screen.getByText('Shared list · Past Projects')).toHaveClass('itg-eyebrow');
        expect(screen.getByRole('heading', {level: 1, name: "This shared list isn't available"})).toBeInTheDocument();
        expect(screen.getByRole('link', {name: 'Search past projects'})).toHaveAttribute('href', '/past-projects');
        expect(screen.getByRole('link', {name: 'Go to Projects'})).toHaveAttribute('href', '/projects');
        expect(screen.queryByRole('button', {name: 'Try again'})).toBeNull();
        expect(screen.queryByTestId('share-title')).toBeNull();
    });

    it('offers to try again, without calling the link wrong, when a shared list fails to load', () => {
        sharedState.shareError = 'Request failed with status code 503';
        sharedState.shareNotFound = false;

        renderPage();

        expect(screen.getByText('Shared list · Past Projects')).toHaveClass('itg-eyebrow');
        expect(screen.getByRole('heading', {level: 1, name: "We couldn't load this shared list"})).toBeInTheDocument();
        expect(screen.queryByRole('heading', {name: "This shared list isn't available"})).toBeNull();
        expect(screen.queryByText(/deleted the list/)).toBeNull();
        expect(screen.getByRole('link', {name: 'Search past projects'})).toHaveAttribute('href', '/past-projects');
        expect(screen.queryByTestId('share-title')).toBeNull();

        fireEvent.click(screen.getByRole('button', {name: 'Try again'}));
        expect(mockRetryShare).toHaveBeenCalledTimes(1);
    });
});
