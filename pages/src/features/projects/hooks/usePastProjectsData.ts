import {useState, useEffect} from 'react';
import {fetchPastProjectArchive} from '@/features/projects/api';
import type {CompactPastProjectRow, PastProjectArchiveQuery} from '@/features/projects/api';
import type {SheetRow} from '@/components/SheetsDataTable';
import {formatSemesterLabel} from '@/lib/format';

function projectToSheetRow(p: CompactPastProjectRow): SheetRow {
    return {
        Track: String(p.track ?? ''),
        Order: String(p.presentation_order ?? ''),
        'Year-Semester': formatSemesterLabel(p.semester_label),
        Class: p.class_code,
        'Team#': p.team_number,
        TeamName: p.team_name,
        'Project Title': p.project_title,
        Organization: p.organization,
        Industry: p.industry,
        Abstract: '',
        'Student Names': '',
        'Showcase Participation': '',
        NameTitle: '',
    };
}

interface UsePastProjectsDataResult {
    rows: SheetRow[];
    loading: boolean;
    error: string | null;
}

export function usePastProjectsData(query: Pick<PastProjectArchiveQuery, 'year' | 'season'> = {}): UsePastProjectsDataResult {
    const [rows, setRows] = useState<SheetRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const {year, season} = query;

    useEffect(() => {
        const controller = new AbortController();
        const load = async () => {
            const projects: CompactPastProjectRow[] = [];
            let page = 1;
            while (true) {
                const payload = await fetchPastProjectArchive({page, page_size: 100, year, season}, controller.signal);
                projects.push(...payload.results);
                if (projects.length >= payload.count) break;
                page += 1;
            }
            return projects;
        };

        load()
            .then((projects) => {
                if (controller.signal.aborted) return;
                setRows(projects.map(projectToSheetRow));
                setError(null);
            })
            .catch((err) => {
                if (controller.signal.aborted) return;
                setError(err instanceof Error ? err.message : 'Failed to load past projects');
            })
            .finally(() => {
                if (!controller.signal.aborted) setLoading(false);
            });

        return () => {
            controller.abort();
        };
    }, [season, year]);

    return {rows, loading, error};
}
