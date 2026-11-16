import {api} from '@/lib/api';
import {authApi} from '@/features/auth';
import {formatSemesterLabel} from '@/lib/format';
import type {PaginatedResponse} from '@/types/api';
import type {ScheduleProjectRow} from '@/features/events/api';
import type {
    ProjectTableRow,
    CompactPastProjectRow,
    ProjectGridRow,
    ProjectDetail,
    SemesterWithProjects,
    SemesterWithFullProjects,
    PastProjectAISearchResponse,
    ProjectAISearchScope,
} from './types';

/** A project or share id as one URL path segment: a route param is decoded, so "../x" or "a?b" must not escape it. */
export const pathSegment = (id: string) => encodeURIComponent(id);

const presentingText = (isPresenting: boolean | null | undefined) =>
    isPresenting == null ? '' : isPresenting ? 'Yes' : 'No';

/**
 * Which list a row came from and the current project an archive row stands in for, as a grid row keeps them: only
 * when the API sent them (rows of /projects/all/, project details and AI search results; not the archive's own).
 */
export const catalogFields = ({catalog, current_project_id}: Pick<ProjectGridRow, 'catalog' | 'current_project_id'>) => ({
    ...(catalog ? {catalog} : {}),
    ...(current_project_id ? {current_project_id} : {}),
});

export const toProjectGridRow = (project: ProjectTableRow): ProjectGridRow => ({
    id: project.id,
    semester_label: formatSemesterLabel(project.semester_label),
    class_code: project.class_code,
    team_number: project.team_number,
    team_name: project.team_name,
    project_title: project.project_title,
    organization: project.organization,
    industry: project.industry,
    abstract: project.abstract,
    student_names: project.student_names,
    is_presenting: presentingText(project.is_presenting),
    ...catalogFields(project),
});

export const scheduleProjectToGridRow = (row: ScheduleProjectRow): ProjectGridRow => ({
    semester_label: formatSemesterLabel(row.year_semester),
    class_code: row.class_code,
    team_number: row.team_number,
    team_name: row.team_name,
    project_title: row.project_title,
    organization: row.organization,
    industry: row.industry,
    abstract: row.abstract,
    student_names: row.student_names,
    is_presenting: row.is_presenting ? 'Yes' : 'No',
});

export const fetchCurrentProjects = async (): Promise<SemesterWithProjects> => {
    const response = await api.get<SemesterWithProjects>('/event/projects/');
    return response.data;
};

export const fetchCurrentProjectsFull = async (): Promise<SemesterWithFullProjects> => {
    const response = await api.get<SemesterWithFullProjects>('/event/projects/');
    return response.data;
};

export const compactProjectToGridRow = (project: CompactPastProjectRow): ProjectGridRow => ({
    id: project.id,
    semester_label: formatSemesterLabel(project.semester_label),
    class_code: project.class_code,
    team_number: project.team_number,
    team_name: project.team_name,
    project_title: project.project_title,
    organization: project.organization,
    industry: project.industry,
    // The abstract is left to the detail endpoint; student names come along when the API sends them, so a search
    // finds a team by its members.
    abstract: '',
    student_names: project.student_names ?? '',
    // Sent on a current-semester row of /projects/all/; null (shown as nothing) on archive rows.
    is_presenting: presentingText(project.is_presenting),
    ...catalogFields(project),
});

export const fetchPastProjects = async (
    page = 1,
    pageSize = 5
): Promise<PaginatedResponse<SemesterWithProjects>> => {
    const response = await api.get<PaginatedResponse<SemesterWithProjects>>(
        `/projects/past/?page=${page}&page_size=${pageSize}`
    );
    return response.data;
};

/** `scope` 'all' also ranks the active schedule's projects, as /projects/all/ lists them; 'past' the archive only. */
export const searchPastProjectsWithAI = async (
    query: string,
    limit = 10,
    scope: ProjectAISearchScope = 'past',
): Promise<PastProjectAISearchResponse> => {
    const response = await authApi.post<PastProjectAISearchResponse>('/projects/past-ai-search/', {
        query,
        limit,
        scope,
    });
    return response.data;
};

export const fetchProjectDetail = async (
    id: string,
    signal?: AbortSignal,
    timeout?: number,
): Promise<ProjectDetail> => {
    const response = await api.get<ProjectDetail>(`/projects/${pathSegment(id)}/`, {signal, timeout});
    return response.data;
};
