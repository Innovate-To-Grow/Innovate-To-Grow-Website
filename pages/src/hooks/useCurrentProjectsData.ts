import {useState, useEffect} from 'react';
import {fetchCurrentProjectsFull} from '../services/api/projects';
import type {ProjectTableRow} from '../services/api/projects';
import type {SheetRow} from '../components/SheetsDataTable';

function projectToSheetRow(p: ProjectTableRow): SheetRow {
  return {
    Track: String(p.track ?? ''),
    Order: String(p.presentation_order ?? ''),
    'Year-Semester': p.semester_label,
    Class: p.class_code,
    'Team#': p.team_number,
    TeamName: p.team_name,
    'Project Title': p.project_title,
    Organization: p.organization,
    Industry: p.industry,
    Abstract: p.abstract,
    'Student Names': p.student_names,
    NameTitle: '',
  };
}

interface UseCurrentProjectsDataResult {
  rows: SheetRow[];
  loading: boolean;
  error: string | null;
}

export function useCurrentProjectsData(): UseCurrentProjectsDataResult {
  const [rows, setRows] = useState<SheetRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchCurrentProjectsFull()
      .then((semester) => {
        if (cancelled) return;
        setRows(semester.projects.map(projectToSheetRow));
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load projects');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return {rows, loading, error};
}
