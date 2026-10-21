import type {ProjectGridRow} from '../projectGrid';
import type {ProjectRowsExporter} from '../export/exportTypes';
import type {ExportTarget} from './curationNote';

type ProjectRowsExportFormat = 'pdf' | 'excel' | 'word';

// Each exporter is its own code-split chunk, loaded on the first click.
async function loadProjectRowsExporter(format: ProjectRowsExportFormat): Promise<ProjectRowsExporter> {
  switch (format) {
    case 'pdf':
      return (await import('../export/pdfExport')).exportProjectRowsPdf;
    case 'excel':
      return (await import('../export/excelExport')).exportProjectRowsExcel;
    case 'word':
      return (await import('../export/wordExport')).exportProjectRowsWord;
  }
}

interface MergedExportGroupProps {
  rows: ProjectGridRow[];
  /** Built on click rather than every render: preparing the note sanitizes and walks the whole note. */
  buildTarget: () => ExportTarget;
  onError: (message: string) => void;
}

export const MergedExportGroup = ({rows, buildTarget, onError}: MergedExportGroupProps) => {
  const handleExport = async (format: ProjectRowsExportFormat, label: string) => {
    try {
      const exporter = await loadProjectRowsExporter(format);
      const {fileBaseName, context} = buildTarget();
      await exporter(rows, fileBaseName, context);
    } catch {
      // Dynamic-import (code-split chunk) or serialization failures otherwise reject silently.
      onError(`Unable to export ${label}. Please try again.`);
    }
  };

  return (
    <div className="project-grid-toolbar-cluster project-grid-export-group" role="group" aria-label="Export">
      <span className="project-grid-group-label" aria-hidden="true">
        Export
      </span>
      <button
        type="button"
        className="itg-btn itg-btn-outline"
        onClick={() => void handleExport('pdf', 'PDF')}
        disabled={!rows.length}
      >
        PDF
      </button>
      <button
        type="button"
        className="itg-btn itg-btn-outline"
        onClick={() => void handleExport('excel', 'Excel')}
        disabled={!rows.length}
      >
        Excel
      </button>
      <button
        type="button"
        className="itg-btn itg-btn-outline"
        onClick={() => void handleExport('word', 'Microsoft Word')}
        disabled={!rows.length}
      >
        <span>
          <span className="project-grid-wide-only">Microsoft</span> Word
        </span>
      </button>
    </div>
  );
};
