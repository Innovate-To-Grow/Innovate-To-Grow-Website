import type { ElementType } from 'react';
import { SheetsDataTable } from '@/components/ui/SheetsDataTable';
import type { SheetRow } from '@/components/ui/SheetsDataTable';

interface ProjectTableData {
  heading?: string;
  heading_level?: number;
  caption?: string;
  rows?: unknown[];
}

// Past-project pages have no Track/Order, and the semester is constant per page,
// so we show the columns the legacy lookup table showed by default.
const COLUMNS: { key: keyof SheetRow; label: string }[] = [
  { key: 'Class', label: 'Class' },
  { key: 'Team#', label: 'Team #' },
  { key: 'TeamName', label: 'Team Name' },
  { key: 'Project Title', label: 'Project Title' },
  { key: 'Organization', label: 'Organization' },
  { key: 'Industry', label: 'Industry' },
];

const ROW_KEYS: (keyof SheetRow)[] = [
  'Track', 'Order', 'Year-Semester', 'Class', 'Team#', 'TeamName', 'Project Title',
  'Organization', 'Industry', 'Abstract', 'Student Names', 'Showcase Participation', 'NameTitle',
];

// Coerce a hardcoded JSON row into a complete SheetRow (every key a string) so the
// table's search/sort/expand logic never hits an undefined value.
function toSheetRow(row: unknown): SheetRow {
  const record = (row && typeof row === 'object') ? (row as Record<string, unknown>) : {};
  const out = {} as SheetRow;
  for (const key of ROW_KEYS) {
    const value = record[key];
    out[key] = value == null ? '' : String(value);
  }
  return out;
}

export const ProjectTableBlock = ({ data }: { data: ProjectTableData }) => {
  const HeadingTag = `h${data.heading_level || 2}` as ElementType;
  const rows = Array.isArray(data.rows) ? data.rows.map(toSheetRow) : [];

  return (
    <section className="cms-project-table">
      {data.heading && <HeadingTag className="section-title">{data.heading}</HeadingTag>}
      {data.caption && <p className="cms-project-table-caption">{data.caption}</p>}
      <SheetsDataTable rows={rows} columns={COLUMNS} />
    </section>
  );
};
