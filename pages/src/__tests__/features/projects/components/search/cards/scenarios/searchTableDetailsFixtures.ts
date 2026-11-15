import {fireEvent, screen} from '@testing-library/react';
import {compactProjectToGridRow, type ProjectDetail, type ProjectGridRow} from '@/features/projects/api';

export function compactRow(id: string): ProjectGridRow {
  return compactProjectToGridRow({
    id, semester_label: '2025-1 Spring', class_code: 'CAP', team_number: id,
    team_name: 'Team', project_title: `Project ${id}`, organization: 'Org', industry: 'Energy',
    track: null, presentation_order: null,
  });
}

export function detail(id: string, fields: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    ...compactRow(id), id, track: null, presentation_order: null, is_presenting: null,
    abstract: `Abstract ${id}`, student_names: `Students ${id}`, ...fields,
  };
}

export function deferredDetail() {
  let resolve!: (value: ProjectDetail) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<ProjectDetail>((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}

/** Shows `count` rows per page, so a page holds more rows than detail requests may run at once. */
export function showRowsPerPage(count: number) {
  fireEvent.change(screen.getByLabelText('Per page'), {target: {value: String(count)}});
}
