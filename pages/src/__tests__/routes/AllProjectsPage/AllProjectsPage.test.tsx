import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {MemoryRouter} from 'react-router';

import {AllProjectsPage} from '@/routes/AllProjectsPage/AllProjectsPage';
import {createPastProjectShare, type PastProjectShare} from '@/features/projects/api';

const {addedRow, archiveRow, currentRow, gridState, mockNavigate} = vi.hoisted(() => {
    const archive = {
        id: '11111111-1111-4111-8111-111111111111',
        semester_label: '2019-1 Spring',
        class_code: 'CAP',
        team_number: '101',
        team_name: 'Team Alpha',
        project_title: 'Archived Project',
        organization: 'Acme',
        industry: 'Technology',
        abstract: '',
        student_names: '',
        is_presenting: '',
        catalog: 'archive' as const,
    };
    return {
        archiveRow: archive,
        currentRow: {
            ...archive,
            id: '33333333-3333-4333-8333-333333333333',
            semester_label: '2026 Fall',
            team_number: '303',
            project_title: 'This Semester Project',
            is_presenting: 'Yes',
            catalog: 'current' as const,
        },
        addedRow: {...archive, id: '22222222-2222-4222-8222-222222222222', project_title: 'Added Project'},
        mockNavigate: vi.fn(),
        gridState: {loading: false, rows: [] as Array<Record<string, unknown>>, allCalls: 0, pastCalls: 0},
    };
});

vi.mock('react-router', async (importOriginal) => {
    const actual = await importOriginal<typeof import('react-router')>();
    return {...actual, useNavigate: () => mockNavigate};
});

vi.mock('@/features/projects/api', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/features/projects/api')>();
    return {...actual, createPastProjectShare: vi.fn()};
});

vi.mock('@/features/projects/hooks/useProjectGridData', () => ({
    useAllProjectGridData: () => {
        gridState.allCalls += 1;
        return {error: null, loading: gridState.loading, rows: gridState.rows, refetch: vi.fn()};
    },
    usePastProjectGridData: () => {
        gridState.pastCalls += 1;
        return {error: null, loading: false, rows: [], refetch: vi.fn()};
    },
}));

// The builder and My Curations as the PastProjectsPage tests stub them: buttons that report what they were given.
vi.mock('@/features/projects/components/builder/composition/PastProjectsBuilder', async () => ({
    PastProjectsBuilder: (await import('@/__tests__/routes/PastProjectsPage/pastProjectsModuleStub'))
        .pastProjectsModuleStub(archiveRow, addedRow).PastProjectsBuilder,
}));
vi.mock('@/features/projects/components/curations/panel/MyCurationsPanel', async () => ({
    MyCurationsPanel: (await import('@/__tests__/routes/PastProjectsPage/pastProjectsModuleStub'))
        .pastProjectsModuleStub(archiveRow, addedRow).MyCurationsPanel,
}));

const SHARE: PastProjectShare = {
    id: 'share-new',
    name: 'Spring finalists',
    rows: [archiveRow],
    note: 'Review note',
    details_text: '',
    version: 1,
    share_url: '/past-projects/share-new',
    can_edit: true,
    created_at: '2026-10-31T00:00:00Z',
};

const renderPage = (entry = '/all-projects') =>
    render(
        <MemoryRouter initialEntries={[entry]}>
            <AllProjectsPage/>
        </MemoryRouter>,
    );

describe('AllProjectsPage', () => {
    beforeEach(() => {
        gridState.loading = false;
        gridState.rows = [currentRow, archiveRow];
        gridState.allCalls = 0;
        gridState.pastCalls = 0;
        mockNavigate.mockReset();
        vi.mocked(createPastProjectShare).mockReset();
    });

    afterEach(() => {
        cleanup();
    });

    it('heads the builder with the size of the whole list, the years it spans and its lede', () => {
        const {container} = renderPage();

        expect(screen.getByRole('heading', {level: 1, name: 'All Projects'})).toBeInTheDocument();
        expect(screen.getByText('2 projects since 2019')).toHaveClass('itg-page-meta');
        expect(
            screen.getByText(
                "Search every Innovate to Grow project, this semester's teams and the archive, check the ones you " +
                    'want, and collect them into a curation. Save it to keep it and share it with a link, or export it.',
            ),
        ).toHaveClass('itg-lead');
        // The embed widget's "Section titles and page header" hides it.
        expect(container.querySelector('header[data-embed-section="page-header"] h1')).toHaveTextContent('All Projects');
        // The chat launcher tucks away over the whole page, its text and cards included (useLauncherYield).
        expect(container.querySelector('.past-projects-page')).toHaveAttribute('data-launcher-avoid', '');
    });

    it('keeps the meta line in place while the list loads', () => {
        gridState.loading = true;
        gridState.rows = [];
        const {container} = renderPage();

        const meta = container.querySelector('.past-projects-header .itg-page-meta') as HTMLElement;
        expect(meta.textContent).toBe('\u00a0');
        expect(meta).toHaveAttribute('aria-hidden', 'true');
    });

    it('builds on every project, under the All Projects words', () => {
        renderPage();

        const builder = screen.getByRole('button', {name: 'Create mocked share'});
        expect(builder).toHaveAttribute('data-catalog', 'all');
        expect(builder).toHaveAttribute('data-rows', 'This Semester Project|Archived Project');
        expect(gridState.allCalls).toBeGreaterThan(0);
        expect(gridState.pastCalls).toBe(0);
    });

    it("lists the member's saved curations above the builder", () => {
        renderPage();

        const curations = screen.getByRole('region', {name: 'My Curations (mocked)'});
        const builder = screen.getByRole('button', {name: 'Create mocked share'});
        expect(curations.compareDocumentPosition(builder) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it("opens a saved curation's page, saying All Projects saved it and handing the curation over", async () => {
        vi.mocked(createPastProjectShare).mockResolvedValue(SHARE);

        renderPage();
        fireEvent.click(screen.getByRole('button', {name: 'Create mocked share'}));

        await waitFor(() => {
            expect(createPastProjectShare).toHaveBeenCalledWith([archiveRow], 'Spring finalists', 'Review note');
            // The share page takes the curation from the state instead of loading it again.
            expect(mockNavigate).toHaveBeenCalledWith('/past-projects/share-new', {
                state: {curationSaved: true, builtOn: '/all-projects', share: SHARE},
            });
        });
    });

    it('passes the ?value= search on to the builder', () => {
        renderPage('/all-projects?value=hydroponics');

        expect(screen.getByRole('button', {name: 'Create mocked share'})).toHaveAttribute(
            'data-initial-search',
            'hydroponics',
        );
    });

    it('names the tab All Projects', () => {
        document.title = 'Spring finalists | Innovate to Grow';
        renderPage();

        expect(document.title).toBe('All Projects | Innovate to Grow');
    });
});
