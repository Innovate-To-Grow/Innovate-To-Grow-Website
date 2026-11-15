import {vi} from 'vitest';

export const {
    addedRow,
    allGridState,
    authState,
    currentRow,
    gridState,
    mockNavigate,
    mockRetryShare,
    sampleRow,
    sharedState,
} = (() => {
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
})();
