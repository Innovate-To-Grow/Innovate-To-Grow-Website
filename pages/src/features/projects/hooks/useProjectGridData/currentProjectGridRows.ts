import {scheduleProjectToGridRow} from '@/features/projects/api';
import {type EventSchedulePayload} from '@/features/events/api';
import {getPredominantTerm} from '../../components/grid/contracts/projectGrid';

/**
 * The schedule lists presenting teams by their schedule slot (whose id is the slot's, not the project's) and
 * the other teams by project. Each row gets the id of its current-semester project (the slot's `project_id`, or
 * the row's own id at track 0), which its title links to. Those are event CurrentProject ids, which the archive
 * detail endpoint does not know: /projects/:id reads them back from this same payload (useProjectDetail).
 */
export const currentScheduleToGridRows = (payload: Pick<EventSchedulePayload, 'projects'> & Partial<EventSchedulePayload>) => {
    const slotProjectIds = new Map<string, string | null>();
    (payload.sections ?? []).forEach((section) =>
        (section.tracks ?? []).forEach((track) =>
            (track.slots ?? []).forEach((slot) => slotProjectIds.set(slot.id, slot.project_id ?? null)),
        ),
    );
    const rows = payload.projects.map((project) => {
        const row = scheduleProjectToGridRow(project);
        const projectId = slotProjectIds.has(project.id)
            ? slotProjectIds.get(project.id)
            : project.track === 0
              ? project.id
              : null;
        return projectId ? {...row, id: projectId} : row;
    });
    // Teams that are not presenting carry no term of their own: they belong to the schedule's semester, and a
    // search for that term ("Fall 2026") should find them too.
    const term = getPredominantTerm(rows);
    return term ? rows.map((row) => (row.semester_label ? row : {...row, semester_label: term})) : rows;
};

export const currentScheduleClassLabels = (payload: Partial<EventSchedulePayload>) => {
    const labels: Record<string, string> = {};
    (payload.sections ?? []).forEach((section) => {
        if (section.code && section.label) labels[section.code] = section.label;
    });
    return labels;
};
