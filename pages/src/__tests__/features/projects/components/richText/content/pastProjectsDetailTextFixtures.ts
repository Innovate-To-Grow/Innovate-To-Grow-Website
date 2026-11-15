import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

export const makeRow = (overrides: Partial<ProjectGridRow> = {}): ProjectGridRow => ({
    id: '',
    semester_label: '2025-1 Spring',
    class_code: 'ENGR 120',
    team_number: 'T01',
    team_name: 'Team Alpha',
    project_title: 'Solar Cart',
    organization: 'Acme',
    industry: 'Energy',
    abstract: 'An abstract.',
    student_names: 'Alice, Bob',
    is_presenting: '',
    ...overrides,
});

export const countProjectBlocks = (html: string) =>
    (html.match(/data-past-project-key=/g) ?? []).length;
