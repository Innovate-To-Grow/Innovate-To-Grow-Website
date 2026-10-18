import type {ProjectGridRow} from '../projectGrid';

export type {ProjectGridRow};

/**
 * Branding shared across the Excel / PDF / Word exporters: the site's UC Merced palette (see the --itg- design
 * tokens). Hex values without "#" (Excel / Word), RGB triples for jsPDF.
 */
/** Navy (--itg-color-primary): titles, section bars, header text. */
export const BRAND_BLUE = '0F2D52';
export const BRAND_BLUE_RGB = [15, 45, 82] as const;
/** Gold (--itg-color-accent-gold): the rule under table headers. */
export const ACCENT_GOLD = 'DBAA00';
export const ACCENT_GOLD_RGB = [219, 170, 0] as const;
/** Body text (--itg-color-text) and secondary text (--itg-color-text-secondary). */
export const TEXT_COLOR = '323336';
export const TEXT_COLOR_RGB = [50, 51, 54] as const;
export const MUTED_TEXT = '555555';
export const MUTED_TEXT_RGB = [85, 85, 85] as const;
/** Row separators and cell borders (--itg-color-border). */
export const TABLE_BORDER = 'DDDDDD';
export const TABLE_BORDER_RGB = [221, 221, 221] as const;
/** Light grey fills: the panel (--itg-color-bg-panel) and the striped table rows (#f9f9f9, as on the site tables). */
export const PANEL_FILL = 'F7F7F7';
export const TABLE_ALT_FILL = 'F9F9F9';
export const TABLE_ALT_FILL_RGB = [249, 249, 249] as const;
/** Inline approximation of the editor's <mark> highlight in document text (--itg-color-tag-new). */
export const HIGHLIGHT_FILL = 'FFE9A8';
export const HIGHLIGHT_FILL_RGB = [255, 233, 168] as const;
/** Amber font color used for highlighted runs in Excel, which has no per-run cell highlight. */
export const HIGHLIGHT_TEXT = '7A5A00';

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
