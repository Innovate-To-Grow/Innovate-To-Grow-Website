import {RichTextDetailEditor} from '../richText/RichTextDetailEditor';
import type {ProjectGridRow} from '../projectGrid';
import {SharedEditIcon, SharedSaveIcon} from '../richText/shareEditorIcons';
import {ProjectNoteInsertControl} from './ProjectNoteInsertControl';
import type {NoteInsertFields} from './useNoteInsertFields';
import type {SharedListEditor} from './useSharedListEditor';

interface SharedNoteEditorProps {
  editor: SharedListEditor;
  rows: ProjectGridRow[];
  noteInsert: NoteInsertFields;
}

/** The shared page's curation note, read-only until "Edit curation note" is pressed. */
export const SharedNoteEditor = ({editor, rows, noteInsert}: SharedNoteEditorProps) => {
  const {isEditingNote} = editor;
  const noteAction = (
    <button
      type="button"
      className={`itg-btn itg-btn-text project-grid-share-editor-icon-button project-grid-share-note-action${
        isEditingNote ? ' is-active' : ''
      }`}
      onClick={() => void editor.noteAction()}
      disabled={editor.isSaving}
    >
      {isEditingNote ? <SharedSaveIcon /> : <SharedEditIcon />}
      {isEditingNote ? 'Save curation note' : 'Edit curation note'}
    </button>
  );

  return (
    <div className={`project-grid-share-editor${isEditingNote ? ' is-editing' : ''}`}>
      <RichTextDetailEditor
        id="past-project-shared-note-editor"
        label="Curation note"
        value={editor.noteDraft}
        placeholder="Add a curation note (shown at the top of the shared page)."
        readOnly={!isEditingNote}
        autoFocus={isEditingNote}
        headerAction={noteAction}
        onChange={editor.setNoteDraft}
      />
      {isEditingNote ? (
        <ProjectNoteInsertControl
          rows={rows}
          excludedFields={noteInsert.excludedFields}
          onInsert={() => editor.setNoteDraft((current) => noteInsert.appendRows(current, rows))}
          onToggleExcludedField={noteInsert.toggleField}
        />
      ) : null}
    </div>
  );
};
