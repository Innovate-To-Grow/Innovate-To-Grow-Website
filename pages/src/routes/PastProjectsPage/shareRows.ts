import type {ProjectGridRow} from '@/features/projects/api';

/** The fields a shared list stores per project; row equality and edits compare exactly these. */
const PROJECT_ROW_FIELDS: Array<keyof ProjectGridRow> = [
  'id',
  'semester_label',
  'class_code',
  'team_number',
  'team_name',
  'project_title',
  'organization',
  'industry',
  'abstract',
  'student_names',
  'is_presenting',
];

export const haveEqualRows = (left: ProjectGridRow[], right: ProjectGridRow[]) =>
  left.length === right.length &&
  left.every((row, index) => PROJECT_ROW_FIELDS.every((field) => row[field] === right[index]?.[field]));

const normalizeRowIdentityValue = (value: unknown) =>
  String(value ?? '').trim().toLocaleLowerCase().replace(/\s+/g, ' ');

/** Which project a row is, independent of where it sits in the list. */
export const projectRowIdentityBase = (row: ProjectGridRow) => {
  const id = normalizeRowIdentityValue(row.id);
  if (id) return `id:${id}`;

  // Legacy snapshots may not have a Project UUID. Mirror the backend's
  // Year-Semester + Class + Team# backfill key so distinct legacy rows never
  // collapse into the same `undefined` map entry.
  const legacyKey = [row.semester_label, row.class_code, row.team_number].map(normalizeRowIdentityValue);
  if (legacyKey.every(Boolean)) return `legacy:${legacyKey.join('\u001f')}`;

  // Malformed historical rows can also be missing part of the stable key.
  // Their full fingerprint still gives each distinct row a deterministic key.
  return `legacy-fallback:${PROJECT_ROW_FIELDS.map((field) => normalizeRowIdentityValue(row[field])).join('\u001f')}`;
};

interface IdentifiedRow {
  key: string;
  row: ProjectGridRow;
}

/** Key each row by its identity plus its occurrence, so a project listed twice keeps two distinct keys. */
const identifyProjectRows = (rows: ProjectGridRow[]): IdentifiedRow[] => {
  const occurrences = new Map<string, number>();
  return rows.map((row) => {
    const base = projectRowIdentityBase(row);
    const occurrence = occurrences.get(base) ?? 0;
    occurrences.set(base, occurrence + 1);
    return {key: `${base}\u001e${occurrence}`, row};
  });
};

/** Per kept row, the fields the submission changed relative to the baseline it was edited from. */
const changedFieldsByKey = (submitted: IdentifiedRow[], baselineByKey: Map<string, ProjectGridRow>) => {
  const changes = new Map<string, Partial<ProjectGridRow>>();
  for (const {key, row: submittedRow} of submitted) {
    const baselineRow = baselineByKey.get(key);
    if (!baselineRow) continue;
    const changed: Partial<ProjectGridRow> = {};
    for (const field of PROJECT_ROW_FIELDS) {
      if (submittedRow[field] !== baselineRow[field]) {
        Object.assign(changed, {[field]: submittedRow[field]});
      }
    }
    if (Object.keys(changed).length > 0) {
      changes.set(key, changed);
    }
  }
  return changes;
};

/** Put the baseline rows the submission reordered back in its order, followed by every other row. */
const applySubmittedOrder = (rebased: ProjectGridRow[], submittedBaselineOrder: string[]) => {
  const identified = identifyProjectRows(rebased);
  const rebasedByKey = new Map(identified.map(({key, row}) => [key, row]));
  const requestedKeys = new Set(submittedBaselineOrder);
  return [
    ...submittedBaselineOrder.flatMap((key) => {
      const row = rebasedByKey.get(key);
      return row ? [row] : [];
    }),
    ...identified.filter(({key}) => !requestedKeys.has(key)).map(({row}) => row),
  ];
};

/**
 * Replay one edit — `submittedRows`, made from `baselineRows` — onto `currentRows`, the version the
 * server holds now (it may have changed since the edit started). Removals, field edits, additions and a
 * reorder carry over; rows someone else added meanwhile are kept.
 */
export const rebaseSubmittedRows = (
  currentRows: ProjectGridRow[],
  baselineRows: ProjectGridRow[],
  submittedRows: ProjectGridRow[],
) => {
  const current = identifyProjectRows(currentRows);
  const baseline = identifyProjectRows(baselineRows);
  const submitted = identifyProjectRows(submittedRows);
  const baselineByKey = new Map(baseline.map(({key, row}) => [key, row]));
  const submittedByKey = new Map(submitted.map(({key, row}) => [key, row]));
  const removedKeys = new Set(baseline.filter(({key}) => !submittedByKey.has(key)).map(({key}) => key));
  const changes = changedFieldsByKey(submitted, baselineByKey);

  const kept = current.filter(({key}) => !removedKeys.has(key));
  const rebased = kept.map(({key, row}) => ({...row, ...(changes.get(key) ?? {})}));
  const currentKeys = new Set(kept.map(({key}) => key));
  for (const {key, row} of submitted) {
    if (!baselineByKey.has(key) && !currentKeys.has(key)) {
      rebased.push(row);
      currentKeys.add(key);
    }
  }

  const baselineSurvivorOrder = baseline.filter(({key}) => submittedByKey.has(key)).map(({key}) => key);
  const submittedBaselineOrder = submitted.filter(({key}) => baselineByKey.has(key)).map(({key}) => key);
  const reordered = baselineSurvivorOrder.some((key, index) => submittedBaselineOrder[index] !== key);
  return reordered ? applySubmittedOrder(rebased, submittedBaselineOrder) : rebased;
};

/** The rows of `rowsToAdd` that `currentRows` does not already list (each project once). */
export const rowsNotYetShared = (currentRows: ProjectGridRow[], rowsToAdd: ProjectGridRow[]) => {
  const existing = new Set(currentRows.map(projectRowIdentityBase));
  return rowsToAdd.filter((row) => {
    const identity = projectRowIdentityBase(row);
    if (existing.has(identity)) return false;
    existing.add(identity);
    return true;
  });
};
