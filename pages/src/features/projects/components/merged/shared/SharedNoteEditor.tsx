import {RichTextDetailEditor} from '../../richText/editor/RichTextDetailEditor';
import type {ProjectGridRow} from '../../grid/contracts/projectGrid';
import {SharedEditIcon, SharedSaveIcon} from '../../richText/editor/shareEditorIcons';
import {ProjectNoteInsertControl} from '../list/ProjectNoteInsertControl';
import type {NoteInsertFields} from '../list/useNoteInsertFields';
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
        placeholder="Add a curation note (shown at the top of this page)."
        readOnly={!isEditingNote}
        autoFocus={isEditingNote}
        headerAction={noteAction}
        onChange={editor.setNoteDraft}
      />
      {isEditingNote ? (
        <ProjectNoteInsertControl
          rows={rows}
          excludedFields={noteInsert.excludedFields}
          insertProblem={noteInsert.insertProblem}
          onInsert={() => noteInsert.insertRows(editor.noteDraft, rows, editor.setNoteDraft)}
          onToggleExcludedField={noteInsert.toggleField}
        />
      ) : null}
    </div>
  );
};
