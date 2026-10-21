import type {SheetRow} from './types';

export interface IdentifiedRow {
  key: string;
  detailId: string;
  row: SheetRow;
}

const normalizeIdentityValue = (value: string) =>
  value.trim().toLocaleLowerCase().replace(/\s+/g, ' ');

const rowIdentityBase = (row: SheetRow) =>
  [
    row['Year-Semester'],
    row.Class,
    row['Team#'],
    row.TeamName,
    row['Project Title'],
  ].map(normalizeIdentityValue).join('\u001f');

const rowIdentity = (row: SheetRow) => {
  const fullFingerprint = Object.keys(row)
    .sort()
    .map((field) => normalizeIdentityValue(row[field as keyof SheetRow]))
    .join('\u001f');
  return `${rowIdentityBase(row)}\u001e${fullFingerprint}`;
};

const stableDomToken = (value: string) => {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
};

/** Key every row by its content, so keys stay stable across insertion, refresh and reordering. */
export function identifyRows(rows: SheetRow[]): IdentifiedRow[] {
  const occurrences = new Map<string, number>();
  return rows.map((row) => {
    const identity = rowIdentity(row);
    const occurrence = occurrences.get(identity) ?? 0;
    occurrences.set(identity, occurrence + 1);
    // The occurrence suffix is used only for byte-for-byte duplicate rows,
    // which have no domain distinction. All meaningful row identity remains
    // stable across insertion, refresh, and reordering.
    const key = occurrence ? `${identity}\u001d${occurrence}` : identity;
    return {
      key,
      detailId: `sdt-detail-${stableDomToken(key)}`,
      row,
    };
  });
}
