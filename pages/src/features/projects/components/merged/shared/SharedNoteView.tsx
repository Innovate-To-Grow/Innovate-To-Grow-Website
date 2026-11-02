import type {ReactNode} from 'react';
import {RichDetailPreview} from '../../richText/content/RichDetailPreview';
import {noteHasContent} from '../list/curationNote';

interface SharedNoteViewProps {
  noteHtml: string;
  /** The owner's Edit Curation Note button, on the label's row. With it, an empty note says there is none. */
  action?: ReactNode;
}

/**
 * A saved curation note as everyone reads it: the "Curation note" label over the note, set off by a rule. A visitor
 * sees nothing for an empty note; its owner sees the label row with their button and a line saying there is none.
 */
export const SharedNoteView = ({noteHtml, action}: SharedNoteViewProps) => {
  const hasNote = noteHasContent(noteHtml);
  if (!hasNote && !action) {
    return null;
  }
  return (
    <div className={`project-grid-shared-note${hasNote ? '' : ' is-empty'}`}>
      <div className="project-grid-shared-note-header">
        <p className="project-grid-shared-note-label">Curation note</p>
        {action}
      </div>
      {hasNote ? (
        <RichDetailPreview className="project-grid-shared-detail-text itg-content" html={noteHtml} />
      ) : (
        <p className="project-grid-shared-note-empty">No curation note yet.</p>
      )}
    </div>
  );
};
