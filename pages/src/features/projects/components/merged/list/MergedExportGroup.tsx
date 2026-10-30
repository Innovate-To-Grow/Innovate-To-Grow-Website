import {useRef, useState, type ReactNode} from 'react';
import type {ProjectGridRow} from '../../grid/contracts/projectGrid';
import type {ProjectRowsExporter} from '../../export/support/exportTypes';
import type {ExportTarget} from './curationNote';

type ProjectRowsExportFormat = 'pdf' | 'excel' | 'word';

const EXPORT_LABELS: Record<ProjectRowsExportFormat, string> = {pdf: 'PDF', excel: 'Excel', word: 'Microsoft Word'};

// Each exporter is its own code-split chunk, loaded on the first click.
async function loadProjectRowsExporter(format: ProjectRowsExportFormat): Promise<ProjectRowsExporter> {
  switch (format) {
    case 'pdf':
      return (await import('../../export/formats/pdfExport')).exportProjectRowsPdf;
    case 'excel':
      return (await import('../../export/formats/excelExport')).exportProjectRowsExcel;
    case 'word':
      return (await import('../../export/formats/wordExport')).exportProjectRowsWord;
  }
}

// How browsers (Chromium, Firefox, Safari) and Vite's preload word a code-split chunk that would not load. The
// exporters load jspdf / exceljs the same way, so this can come from inside an export too.
const CODE_LOAD_FAILURE = /dynamically imported module|importing a module script failed|unable to preload/i;

const isCodeLoadFailure = (error: unknown) => error instanceof Error && CODE_LOAD_FAILURE.test(error.message);

interface MergedExportGroupProps {
  rows: ProjectGridRow[];
  /** Built on click rather than every render: preparing the note sanitizes and walks the whole note. */
  buildTarget: () => ExportTarget;
  /** Reports an export's progress and failure; '' clears the line once an export succeeds. */
  onStatus: (message: string) => void;
  /** Said after "Reload the page" when this page's work survives a reload (e.g. the builder's kept draft). */
  reloadNote?: string;
}

export const MergedExportGroup = ({rows, buildTarget, onStatus, reloadNote}: MergedExportGroupProps) => {
  const [pendingFormat, setPendingFormat] = useState<ProjectRowsExportFormat | null>(null);
  const [needsReload, setNeedsReload] = useState(false);
  // Set synchronously, so a second click before the re-render does not start a second download.
  const isExportingRef = useRef(false);

  const handleExport = async (format: ProjectRowsExportFormat) => {
    if (isExportingRef.current) {
      return;
    }
    isExportingRef.current = true;
    setPendingFormat(format);
    const label = EXPORT_LABELS[format];
    onStatus(`Preparing ${label}…`);
    let loaded = false;
    try {
      const exporter = await loadProjectRowsExporter(format);
      loaded = true;
      const {fileBaseName, context} = buildTarget();
      await exporter(rows, fileBaseName, context);
      onStatus('');
    } catch (error) {
      if (!loaded || isCodeLoadFailure(error)) {
        // The site was updated since this page loaded (the old chunk is gone), or a download failed. Trying
        // again cannot help: browsers keep a module that failed to load (Safari even without asking again).
        setNeedsReload(true);
        onStatus(
          `Unable to export ${label}: part of this page did not download, often because the site was updated. ` +
            `Reload the page, then export again.${reloadNote ? ` ${reloadNote}` : ''}`,
        );
      } else {
        onStatus(`Unable to export ${label}. Please try again.`);
      }
    } finally {
      isExportingRef.current = false;
      setPendingFormat(null);
    }
  };

  // aria-disabled (not disabled) while exporting keeps keyboard focus on the button that was pressed.
  const exportButton = (format: ProjectRowsExportFormat, content: ReactNode) => (
    <button
      type="button"
      className="itg-btn itg-btn-outline"
      onClick={() => void handleExport(format)}
      disabled={!rows.length}
      aria-disabled={pendingFormat ? true : undefined}
    >
      {content}
    </button>
  );

  return (
    <div
      className="project-grid-toolbar-cluster project-grid-export-group"
      role="group"
      aria-label="Export"
      aria-busy={pendingFormat ? true : undefined}
    >
      <span className="project-grid-group-label" aria-hidden="true">
        Export
      </span>
      {exportButton('pdf', 'PDF')}
      {exportButton('excel', 'Excel')}
      {exportButton(
        'word',
        <span>
          <span className="project-grid-wide-only">Microsoft</span> Word
        </span>,
      )}
      {needsReload ? (
        <button type="button" className="itg-btn itg-btn-text" onClick={() => window.location.reload()}>
          Reload page
        </button>
      ) : null}
    </div>
  );
};
