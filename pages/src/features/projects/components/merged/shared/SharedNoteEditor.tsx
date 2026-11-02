import {useEffect, useRef} from 'react';
import {RichTextDetailEditor} from '../../richText/editor/RichTextDetailEditor';
import type {ProjectGridRow} from '../../grid/contracts/projectGrid';
import {SharedEditIcon, SharedSaveIcon} from '../../richText/editor/shareEditorIcons';
import {ProjectNoteInsertControl} from '../list/ProjectNoteInsertControl';
import type {NoteInsertFields} from '../list/useNoteInsertFields';
import {SharedNoteView} from './SharedNoteView';
import type {SharedListEditor} from './useSharedListEditor';

interface SharedNoteEditorProps {
  editor: SharedListEditor;
  rows: ProjectGridRow[];
  noteInsert: NoteInsertFields;
  /** The saved note, shown until Edit Curation Note is pressed. */
  noteHtml: string;
}

const NOTE_ACTION_CLASS = 'itg-btn itg-btn-text project-grid-share-editor-icon-button project-grid-share-note-action';

/**
 * The owner's curation note: read as visitors see it, with Edit Curation Note on its label row. The editor takes
 * its place while editing, and closing it hands focus back to Edit Curation Note.
 */
export const SharedNoteEditor = ({editor, rows, noteInsert, noteHtml}: SharedNoteEditorProps) => {
  const {isEditingNote} = editor;
  const editButtonRef = useRef<HTMLButtonElement>(null);
  const wasEditingRef = useRef(isEditingNote);

  // Closing the editor (a save, an unchanged note, a newer saved note) removes the Save button that had focus. Put
  // focus on Edit Curation Note in its place, unless focus already went somewhere else (the name editor).
  useEffect(() => {
    const closed = wasEditingRef.current && !isEditingNote;
    wasEditingRef.current = isEditingNote;
    if (closed && (document.activeElement === null || document.activeElement === document.body)) {
      editButtonRef.current?.focus();
    }
  }, [isEditingNote]);

  if (!isEditingNote) {
    return (
      <SharedNoteView
        noteHtml={noteHtml}
        action={
          <button
            ref={editButtonRef}
            type="button"
            className={NOTE_ACTION_CLASS}
            onClick={() => void editor.noteAction()}
            disabled={editor.isSaving}
          >
            <SharedEditIcon />
            <span>Edit Curation Note</span>
          </button>
        }
      />
    );
  }

  return (
    <div className="project-grid-share-editor is-editing">
      <RichTextDetailEditor
        id="past-project-shared-note-editor"
        label="Curation note"
        value={editor.noteDraft}
        placeholder="Add a curation note (shown at the top of this page)."
        autoFocus
        headerAction={
          <button
            type="button"
            className={`${NOTE_ACTION_CLASS} is-active`}
            onClick={() => void editor.noteAction()}
            disabled={editor.isSaving}
          >
            <SharedSaveIcon />
            <span>Save Curation Note</span>
          </button>
        }
        onChange={editor.setNoteDraft}
      />
      <ProjectNoteInsertControl
        rows={rows}
        excludedFields={noteInsert.excludedFields}
        insertProblem={noteInsert.insertProblem}
        onInsert={() => noteInsert.insertRows(editor.noteDraft, rows, editor.setNoteDraft)}
        onToggleExcludedField={noteInsert.toggleField}
      />
    </div>
  );
};
