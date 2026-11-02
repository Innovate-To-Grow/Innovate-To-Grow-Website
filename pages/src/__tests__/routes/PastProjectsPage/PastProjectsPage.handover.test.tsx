import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {MemoryRouter, Route, Routes, useNavigate, type InitialEntry} from 'react-router';

import {AllProjectsPage} from '@/routes/AllProjectsPage/AllProjectsPage';
import {PastProjectsPage} from '@/routes/PastProjectsPage/PastProjectsPage';
import {createPastProjectShare, fetchPastProjectShare, type PastProjectShare} from '@/features/projects/api';

// All Projects' save hands the curation it created over to the share page, which opens with it instead of asking the
// server for it again. The share page's own data hook (usePastProjectShareData) is the real one here.

const {addedRow, archiveRow, currentRow} = vi.hoisted(() => {
    const archive = {
        id: '11111111-1111-4111-8111-111111111111',
        semester_label: '2019 Spring',
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
    };
});

vi.mock('@/features/projects/api', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/features/projects/api')>();
    return {
        ...actual,
        createPastProjectShare: vi.fn(),
        fetchPastProjectShare: vi.fn(),
        updatePastProjectShare: vi.fn(),
    };
});

// The builders' lists are not what this is about; the share's own load is real.
vi.mock('@/features/projects/hooks/useProjectGridData', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/features/projects/hooks/useProjectGridData')>();
    const list = () => ({error: null, loading: false, rows: [], refetch: () => undefined});
    return {...actual, useAllProjectGridData: list, usePastProjectGridData: list};
});

vi.mock('@/features/projects', async () =>
    (await import('@/__tests__/routes/PastProjectsPage/pastProjectsModuleStub')).pastProjectsModuleStub(
        archiveRow,
        addedRow,
    ),
);
vi.mock('@/features/projects/components/builder/composition/PastProjectsBuilder', async () => ({
    PastProjectsBuilder: (await import('@/__tests__/routes/PastProjectsPage/pastProjectsModuleStub'))
        .pastProjectsModuleStub(archiveRow, addedRow).PastProjectsBuilder,
}));
vi.mock('@/features/projects/components/curations/panel/MyCurationsPanel', async () => ({
    MyCurationsPanel: (await import('@/__tests__/routes/PastProjectsPage/pastProjectsModuleStub'))
        .pastProjectsModuleStub(archiveRow, addedRow).MyCurationsPanel,
}));

const shareFixture = (overrides: Partial<PastProjectShare> = {}): PastProjectShare => ({
    id: 'share-new',
    name: 'Spring finalists',
    rows: [archiveRow, currentRow],
    note: 'Review note',
    details_text: '',
    version: 1,
    share_url: '/past-projects/share-new',
    can_edit: true,
    created_at: '2026-10-31T00:00:00Z',
    ...overrides,
});

/** Opens a page with a share in the state, as a save would, but at another curation's address. */
const OpenOtherCuration = ({share}: {share: PastProjectShare}) => {
    const navigate = useNavigate();
    return (
        <button type="button" onClick={() => navigate('/past-projects/share-other', {state: {curationSaved: true, share}})}>
            Open another curation
        </button>
    );
};

const renderApp = (entry: InitialEntry, share: PastProjectShare = shareFixture()) =>
    render(
        <MemoryRouter initialEntries={[entry]}>
            <Routes>
                <Route path="/all-projects" element={<AllProjectsPage/>}/>
                <Route path="/elsewhere" element={<OpenOtherCuration share={share}/>}/>
                <Route path="/past-projects/:shareId" element={<PastProjectsPage/>}/>
            </Routes>
        </MemoryRouter>,
    );

describe('PastProjectsPage — a curation handed over by its save', () => {
    beforeEach(() => {
        vi.mocked(createPastProjectShare).mockReset();
        vi.mocked(fetchPastProjectShare).mockReset();
    });

    afterEach(() => {
        cleanup();
    });

    it('opens the curation All Projects just saved without loading it again', async () => {
        vi.mocked(createPastProjectShare).mockResolvedValue(shareFixture());
        vi.mocked(fetchPastProjectShare).mockResolvedValue(shareFixture({name: 'Loaded again'}));

        renderApp('/all-projects');
        fireEvent.click(screen.getByRole('button', {name: 'Create mocked share'}));

        expect(await screen.findByTestId('share-title')).toHaveTextContent('Spring finalists');
        await act(async () => {});
        expect(fetchPastProjectShare).not.toHaveBeenCalled();
        expect(screen.getByTestId('share-title')).toHaveTextContent('Spring finalists');
        expect(screen.getByTestId('share-note')).toHaveTextContent('Review note');
        expect(screen.getByText(/^Curation saved\./)).toHaveTextContent('on the All Projects page');
        // The owner's search for more projects is there at once, the share being loaded.
        expect(screen.getByRole('button', {name: 'Add mocked row'})).toBeInTheDocument();
        expect(screen.queryByText('Loading curation…')).toBeNull();
    });

    it('loads a curation whose history entry a reload or Back/Forward restores, which may be outdated', async () => {
        vi.mocked(fetchPastProjectShare).mockResolvedValue(shareFixture({name: 'Renamed since', version: 3}));

        renderApp({
            pathname: '/past-projects/share-new',
            state: {curationSaved: true, builtOn: '/all-projects', share: shareFixture()},
        });

        expect(await screen.findByTestId('share-title')).toHaveTextContent('Renamed since');
        expect(fetchPastProjectShare).toHaveBeenCalledTimes(1);
        expect(fetchPastProjectShare).toHaveBeenCalledWith('share-new');
    });

    it('loads the curation at the address when the state holds another one', async () => {
        vi.mocked(fetchPastProjectShare).mockResolvedValue(shareFixture({id: 'share-other', name: 'The other one'}));

        renderApp('/elsewhere');
        fireEvent.click(screen.getByRole('button', {name: 'Open another curation'}));

        expect(await screen.findByTestId('share-title')).toHaveTextContent('The other one');
        expect(screen.queryByText('Spring finalists')).toBeNull();
        expect(fetchPastProjectShare).toHaveBeenCalledWith('share-other');
    });
});
