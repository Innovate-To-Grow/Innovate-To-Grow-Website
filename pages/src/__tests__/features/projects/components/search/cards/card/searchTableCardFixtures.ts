import {screen} from '@testing-library/react';

import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

export const makeRow = (overrides: Partial<ProjectGridRow> = {}): ProjectGridRow => ({
    semester_label: '2025-1 Spring',
    class_code: 'ENGR 120',
    team_number: 'T01',
    team_name: 'Team Alpha',
    project_title: 'Alpha Project',
    organization: 'Acme',
    industry: 'Technology',
    abstract: 'An abstract',
    student_names: 'Alice',
    is_presenting: '',
    ...overrides,
});

export const makeRows = (count = 3): ProjectGridRow[] =>
    Array.from({length: count}, (_, index) =>
        makeRow({
            team_number: `T0${index + 1}`,
            team_name: `Team ${index + 1}`,
            project_title: `Project ${index + 1}`,
        }),
    );

export const cardSection = (container: HTMLElement) =>
    container.querySelector('.search-table-card') as HTMLElement;

export const rowCheckbox = (title: string) => screen.getAllByLabelText(`Select ${title}`)[0];

export const deferred = <T,>() => {
    let resolve!: (value: T) => void;
    let reject!: (reason: unknown) => void;
    const promise = new Promise<T>((res, rej) => {
        resolve = res;
        reject = rej;
    });
    return {promise, resolve, reject};
};
