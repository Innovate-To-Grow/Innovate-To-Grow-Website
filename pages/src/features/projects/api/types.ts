// Types for the projects API: project rows and details, the past-project archive, and shares.

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

export interface CompactPastProjectRow {
    id: string;
    semester_label: string;
    class_code: string;
    team_number: string;
    team_name: string;
    project_title: string;
    organization: string;
    industry: string;
    track: number | null;
    presentation_order: number | null;
}

export interface PastProjectArchiveQuery {
    page?: number;
    page_size?: number;
    search?: string;
    year?: number;
    season?: 1 | 2;
    semester?: string;
}

export interface ProjectGridRow {
    id?: string;
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
    details_text: string;
    version: number;
    share_url: string;
    can_edit: boolean;
    created_at: string;
}

export interface PastProjectShareSummary {
    id: string;
    name: string;
    note: string;
    version: number;
    share_url: string;
    row_count: number;
    created_at: string;
    /** When the curation last changed. Absent from servers that predate it. */
    updated_at?: string;
}

export interface PastProjectAISearchResponse {
    available: boolean;
    message?: string;
    query: string;
    results: ProjectTableRow[];
    usage?: {
        inputTokens?: number;
        outputTokens?: number;
        totalTokens?: number;
    };
}

export interface ProjectGridHydrationResult {
    rows: ProjectGridRow[];
    /** Input indexes whose details still failed after retries (worth trying again); returned unchanged. */
    failedIndexes: number[];
    /**
     * Input indexes the detail endpoint refused outright, e.g. a 404 for a project that was removed or whose
     * semester is unpublished. Retrying cannot help; returned unchanged.
     */
    unavailableIndexes: number[];
}
