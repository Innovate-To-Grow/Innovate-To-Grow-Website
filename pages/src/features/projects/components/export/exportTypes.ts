import type {ProjectGridRow} from '../projectGrid';

export type {ProjectGridRow};

/** Branding shared across the Excel / PDF / Word exporters. */
export const BRAND_BLUE = '0F2D52';
export const BRAND_BLUE_RGB = [15, 45, 82] as const;
export const BORDER_BLUE = 'BDD3EA';
export const LIGHT_BLUE = 'EAF4FF';
export const TABLE_ALT_FILL = 'F7FAFC';

export const I2G_LOGO_URL = '/assets/images/i2glogo.png';

/** Tabular columns shared by every export (one row per project). */
export const EXPORT_COLUMNS = [
  'Year-Semester',
  'Class',
  'Team#',
  'Team Name',
  'Project Title',
  'Organization',
  'Industry',
  'Abstract',
  'Student Names',
] as const;

export interface ProjectRowsExportContext {
  note?: string;
  title?: string;
}

export interface ExportLogoAsset {
  base64: string;
  bytes: Uint8Array;
  dataUrl: string;
  extension: 'png';
}

export type ProjectRowsExporter = (
  rows: ProjectGridRow[],
  fileBaseName: string,
  context?: ProjectRowsExportContext,
) => Promise<void>;

export const normalizeProjectRowsExportContext = (context: ProjectRowsExportContext = {}) => ({
  note: (context.note ?? '').trim(),
  title: context.title?.trim() || 'Past Projects',
});

export const toDisplayValue = (value: string | number | null | undefined) => String(value ?? '').trim();

export const triggerDownload = (blob: Blob, fileName: string) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};
