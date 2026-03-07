import api from './client';

export interface ProjectSummary {
  id: string;
  project_title: string;
  team_name: string;
  organization: string;
  industry: string;
  class_code: string;
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

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export const fetchCurrentProjects = async (): Promise<SemesterWithProjects> => {
  const response = await api.get<SemesterWithProjects>('/projects/current/');
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
