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
    allGridState,
    authState,
    currentRow,
    gridState,
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
        currentRow: {
            ...sample,
            id: '33333333-3333-4333-8333-333333333333',
            semester_label: '2026 Fall',
            team_number: '303',
            team_name: 'Team Gamma',
            project_title: 'This Semester Project',
            catalog: 'current' as const,
        },
        authState: {user: null as {member_uuid: string} | null},
        // Each hook call's `enabled`, so a test can tell which list the page asked for.
        gridState: {loading: false, rows: [sample] as Array<typeof sample>, enabled: [] as boolean[]},
        allGridState: {rows: [] as Array<Record<string, unknown>>, enabled: [] as boolean[]},
    };
});

vi.mock('@/features/auth', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/features/auth')>();
    return {...actual, useAuth: () => ({...actual.useAuth(), user: authState.user})};
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
}));

vi.mock('@/features/projects', async () =>
    (await import('@/__tests__/routes/PastProjectsPage/pastProjectsModuleStub')).pastProjectsModuleStub(
        sampleRow,
        addedRow,
    ),
);

// The builder page's body (CatalogBuilderView) imports these two directly.
vi.mock('@/features/projects/components/builder/composition/PastProjectsBuilder', async () => ({
    PastProjectsBuilder: (await import('@/__tests__/routes/PastProjectsPage/pastProjectsModuleStub'))
        .pastProjectsModuleStub(sampleRow, addedRow).PastProjectsBuilder,
}));
vi.mock('@/features/projects/components/curations/panel/MyCurationsPanel', async () => ({
    MyCurationsPanel: (await import('@/__tests__/routes/PastProjectsPage/pastProjectsModuleStub'))
        .pastProjectsModuleStub(sampleRow, addedRow).MyCurationsPanel,
}));

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
        authState.user = null;
        gridState.loading = false;
        gridState.rows = [sampleRow];
        gridState.enabled = [];
        allGridState.rows = [currentRow, sampleRow];
        allGridState.enabled = [];
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

    it("asks again whether the viewer may edit a curation once they sign out or switch accounts", () => {
        // can_edit is the server's answer for whoever was signed in when the curation loaded.
        authState.user = {member_uuid: 'owner-1'};
        sharedState.share = shareFixture();
        const {rerender} = renderPage();
        rerender(
            <MemoryRouter initialEntries={['/past-projects']}>
                <PastProjectsPage/>
            </MemoryRouter>,
        );
        expect(mockRetryShare).not.toHaveBeenCalled();

        authState.user = null;
        rerender(
            <MemoryRouter initialEntries={['/past-projects']}>
                <PastProjectsPage/>
            </MemoryRouter>,
        );
        expect(mockRetryShare).toHaveBeenCalledTimes(1);

        authState.user = {member_uuid: 'someone-else'};
        rerender(
            <MemoryRouter initialEntries={['/past-projects']}>
                <PastProjectsPage/>
            </MemoryRouter>,
        );
        expect(mockRetryShare).toHaveBeenCalledTimes(2);
    });

    it('titles a share stored without a name with the default curation title', async () => {
        sharedState.share = shareFixture({name: '  '});

        renderPage();

        expect(await screen.findByTestId('share-title')).toHaveTextContent('Past Project Curation');
    });

    it('titles a share of current-semester projects stored without a name as the server would name it', async () => {
        sharedState.share = shareFixture({name: '', rows: [sampleRow, currentRow]});

        renderPage();

        expect(await screen.findByTestId('share-title')).toHaveTextContent(/^Project Curation$/);
        expect(document.title).toBe('Project Curation | Innovate to Grow');
        expect(screen.getByRole('link', {name: 'Search all projects'})).toHaveAttribute('href', '/all-projects');
    });

    it('names the tab Past Projects even after a curation page named it', () => {
        // Both routes share the route title, so the route alone would not set it again.
        document.title = 'Spring finalists | Innovate to Grow';
        renderPage();

        expect(document.title).toBe('Past Projects | Innovate to Grow');
    });

    it('heads the builder with the archive size, the years it spans and a lede', () => {
        renderPage();

        expect(screen.getByRole('heading', {level: 1, name: 'Past Projects'})).toBeInTheDocument();
        expect(screen.getByText('1 project since 2025')).toHaveClass('itg-page-meta');
        expect(screen.getByText(/^Search past Innovate to Grow projects, check the ones you want/)).toHaveClass('itg-lead');
    });

    it('keeps the meta line in place while the archive loads, so the lede and builder do not move down', () => {
        gridState.loading = true;
        gridState.rows = [];
        const {container} = renderPage();

        const header = container.querySelector('.past-projects-header') as HTMLElement;
        const meta = header.querySelector('.itg-page-meta') as HTMLElement;
        expect(meta.textContent).toBe('\u00a0');
        expect(meta).toHaveAttribute('aria-hidden', 'true');
        expect(meta.nextElementSibling).toHaveClass('itg-lead');
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
        expect(screen.getByText(/^Curation saved\./)).toHaveAttribute('role', 'status');
        expect(screen.getByText(/^Curation saved\./)).toHaveTextContent(
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

    it('names All Projects in the saved notice of a curation All Projects saved', () => {
        sharedState.share = shareFixture();
        render(
            <MemoryRouter
                initialEntries={[
                    {pathname: '/past-projects/share-abc', state: {curationSaved: true, builtOn: '/all-projects'}},
                ]}
            >
                <PastProjectsPage/>
            </MemoryRouter>,
        );

        expect(screen.getByText(/^Curation saved\./)).toHaveTextContent(
            'Curation saved. It is listed under My Curations on the All Projects page, and you can keep editing it here.',
        );
        expect(screen.getByRole('link', {name: 'All Projects'})).toHaveAttribute('href', '/all-projects');
    });

    it('names Past Projects in the saved notice when the save names no other builder', () => {
        sharedState.share = shareFixture();
        render(
            <MemoryRouter
                initialEntries={[
                    {pathname: '/past-projects/share-abc', state: {curationSaved: true, builtOn: '/somewhere-else'}},
                ]}
            >
                <PastProjectsPage/>
            </MemoryRouter>,
        );

        expect(screen.getByRole('link', {name: 'Past Projects'})).toHaveAttribute('href', '/past-projects');
        expect(screen.queryByRole('link', {name: 'All Projects'})).toBeNull();
    });

    it('builds on the archive under the Past Projects words, without loading every project', () => {
        renderPage();

        const builder = screen.getByRole('button', {name: 'Create mocked share'});
        expect(builder).toHaveAttribute('data-catalog', 'past');
        expect(builder).toHaveAttribute('data-rows', 'Shared Project');
        expect(gridState.enabled).toContain(true);
        expect(allGridState.enabled).not.toContain(true);
    });

    it("lets a curation's owner add from every project, worded as All Projects", () => {
        sharedState.share = shareFixture();

        renderPage();

        // Every project holds whatever either builder saved, this semester's teams too.
        const search = screen.getByRole('button', {name: 'Add mocked row'});
        expect(search).toHaveAttribute('data-catalog', 'all');
        expect(search).toHaveAttribute('data-rows', 'This Semester Project|Shared Project');
        expect(allGridState.enabled).toContain(true);
        expect(gridState.enabled).not.toContain(true);
    });

    it('loads no list for a visitor who cannot edit the curation', () => {
        sharedState.share = shareFixture({can_edit: false});

        renderPage();

        expect(screen.queryByRole('button', {name: 'Add mocked row'})).toBeNull();
        expect(gridState.enabled).not.toContain(true);
        expect(allGridState.enabled).not.toContain(true);
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

        expect(screen.getByText('Curation · Past Projects')).toHaveClass('itg-eyebrow');
        expect(screen.getByRole('heading', {level: 1, name: "This curation isn't available"})).toBeInTheDocument();
        expect(screen.getByRole('link', {name: 'Search past projects'})).toHaveAttribute('href', '/past-projects');
        expect(screen.getByRole('link', {name: 'Go to Projects'})).toHaveAttribute('href', '/projects');
        expect(screen.queryByRole('button', {name: 'Try again'})).toBeNull();
        expect(screen.queryByTestId('share-title')).toBeNull();
    });

    it('offers to try again, without calling the link wrong, when a shared list fails to load', () => {
        sharedState.shareError = 'Request failed with status code 503';
        sharedState.shareNotFound = false;

        renderPage();

        expect(screen.getByText('Curation · Past Projects')).toHaveClass('itg-eyebrow');
        expect(screen.getByRole('heading', {level: 1, name: "We couldn't load this curation"})).toBeInTheDocument();
        expect(screen.queryByRole('heading', {name: "This curation isn't available"})).toBeNull();
        expect(screen.queryByText(/deleted the list/)).toBeNull();
        expect(screen.getByRole('link', {name: 'Search past projects'})).toHaveAttribute('href', '/past-projects');
        expect(screen.queryByTestId('share-title')).toBeNull();

        fireEvent.click(screen.getByRole('button', {name: 'Try again'}));
        expect(mockRetryShare).toHaveBeenCalledTimes(1);
    });
});
