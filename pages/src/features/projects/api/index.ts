import { api } from '@/lib/api-client';
import {getAccessToken} from '@/features/auth';
import {formatSemesterLabel} from '@/lib/semester';
import type { PaginatedResponse } from '@/types/api';
import type { ScheduleProjectRow } from '@/features/events/api';

export type { PaginatedResponse } from '@/types/api';

export interface ProjectSummary {
  id: string;
  project_title: string;
  team_name: string;
  organization: string;
  industry: string;
  class_code: string;
}

export interface ProjectTableRow {
  id: string;
  semester_label: string;
  class_code: string;
  team_number: string;
  team_name: string;
  project_title: string;
  organization: string;
  industry: string;
  abstract: string;
  student_names: string;
  is_presenting?: boolean;
  track: number | null;
  presentation_order: number | null;
}

export interface ProjectGridRow {
  semester_label: string;
  class_code: string;
  team_number: string;
  team_name: string;
  project_title: string;
  organization: string;
  industry: string;
  abstract: string;
  student_names: string;
  is_presenting: string;
}

export interface ProjectDetail {
  id: string;
  project_title: string;
  team_name: string;
  team_number: string;
  organization: string;
  industry: string;
  abstract: string;
  student_names: string;
  class_code: string;
  track: number | null;
  presentation_order: number | null;
  semester_label: string;
}

export interface SemesterWithProjects {
  id: string;
  year: number;
  season: number;
  label: string;
  projects: ProjectSummary[];
}

export interface SemesterWithFullProjects {
  id: string;
  year: number;
  season: number;
  label: string;
  projects: ProjectTableRow[];
}

export interface PastProjectShare {
  id: string;
  name: string;
  rows: ProjectGridRow[];
  note: string;
  share_url: string;
  created_at: string;
}

export interface PastProjectShareSummary {
  id: string;
  name: string;
  note: string;
  share_url: string;
  row_count: number;
  created_at: string;
}

export const toProjectGridRow = (project: ProjectTableRow): ProjectGridRow => ({
  semester_label: formatSemesterLabel(project.semester_label),
  class_code: project.class_code,
  team_number: project.team_number,
  team_name: project.team_name,
  project_title: project.project_title,
  organization: project.organization,
  industry: project.industry,
  abstract: project.abstract,
  student_names: project.student_names,
  is_presenting: project.is_presenting == null ? '' : project.is_presenting ? 'Yes' : 'No',
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

export const fetchAllPastProjects = async (): Promise<ProjectTableRow[]> => {
  const response = await api.get<ProjectTableRow[]>('/projects/past-all/');
  return response.data;
};

export const fetchPastProjects = async (
  page = 1,
  pageSize = 5
): Promise<PaginatedResponse<SemesterWithProjects>> => {
  const response = await api.get<PaginatedResponse<SemesterWithProjects>>(
    `/projects/past/?page=${page}&page_size=${pageSize}`
  );
  return response.data;
};

export const fetchProjectDetail = async (id: string): Promise<ProjectDetail> => {
  const response = await api.get<ProjectDetail>(`/projects/${id}/`);
  return response.data;
};

export const createPastProjectShare = async (
  rows: ProjectGridRow[],
  name: string,
  note: string,
): Promise<PastProjectShare> => {
  // Creating a share is login-only; attach the JWT explicitly (the shared api client
  // does not, matching the events feature's authHeaders() pattern).
  const token = getAccessToken();
  const response = await api.post<PastProjectShare>(
    '/projects/past-shares/',
    {rows, name, note},
    token ? {headers: {Authorization: `Bearer ${token}`}} : {},
  );
  return response.data;
};

export const fetchPastProjectShare = async (id: string): Promise<PastProjectShare> => {
  const response = await api.get<PastProjectShare>(`/projects/past-shares/${id}/`);
  return response.data;
};

export const listMyShares = async (): Promise<PastProjectShareSummary[]> => {
  const token = getAccessToken();
  const response = await api.get<PastProjectShareSummary[]>(
    '/projects/past-shares/mine/',
    token ? {headers: {Authorization: `Bearer ${token}`}} : {},
  );
  return response.data;
};

export const deleteShare = async (id: string): Promise<void> => {
  const token = getAccessToken();
  await api.delete(
    `/projects/past-shares/${id}/`,
    token ? {headers: {Authorization: `Bearer ${token}`}} : {},
  );
};
