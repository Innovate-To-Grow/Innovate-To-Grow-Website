import {useId, type ReactNode} from 'react';
import {RichTextDetailEditor} from '../../richText/editor/RichTextDetailEditor';
import type {ProjectGridRow} from '../../grid/contracts/projectGrid';
import {curationBranding} from '../list/curationBranding';
import type {SignInToSave} from '../list/curationNote';
import {ProjectNoteInsertControl} from '../list/ProjectNoteInsertControl';
import type {NoteInsertFields} from '../list/useNoteInsertFields';
import {SignInToSaveLink} from '../list/SignInToSaveLink';

interface CurationSaveButtonProps {
  hasRows: boolean;
  isSharing: boolean;
  pendingSaveCount: number;
  onSave: () => void;
}

// Saving creates the curation's page: it is listed under My Curations, and its link can be passed on. The
// button is at the top of the card and again under the note.
export const CurationSaveButton = ({hasRows, isSharing, pendingSaveCount, onSave}: CurationSaveButtonProps) => (
  <button
    type="button"
    className="itg-btn itg-btn-primary"
    onClick={onSave}
    disabled={!hasRows || isSharing || pendingSaveCount > 0}
  >
    {isSharing ? 'Saving…' : 'Save Curation'}
  </button>
);

interface CurationSaveSectionProps {
  isAuthenticated: boolean;
  rows: ProjectGridRow[];
  nameDraft: string;
  noteDraft: string;
  onNameDraftChange: (name: string) => void;
  onNoteDraftChange: (note: string) => void;
  noteInsert: NoteInsertFields;
  saveButton: ReactNode;
  pendingSaveCount: number;
  signIn: SignInToSave;
}

export const CurationSaveSection = ({
  isAuthenticated,
  rows,
  nameDraft,
  noteDraft,
  onNameDraftChange,
  onNoteDraftChange,
  noteInsert,
  saveButton,
  pendingSaveCount,
  signIn,
}: CurationSaveSectionProps) => {
  const nameInputId = useId();
  const nameHintId = useId();

  return (
    <div className="project-grid-share">
      <h3 className="project-grid-share-title">Save this curation</h3>
      {isAuthenticated ? (
        <>
          <div className="project-grid-share-fields">
            <div className="itg-field project-grid-share-note project-grid-share-name">
              <label className="project-grid-share-note-label" htmlFor={nameInputId}>
                Curation name <span className="project-grid-label-hint">(optional)</span>
              </label>
              <input
                id={nameInputId}
                type="text"
                className="itg-input project-grid-share-name-input"
                value={nameDraft}
                maxLength={200}
                // The name the server gives a curation saved without one, for the rows it would save.
                placeholder={curationBranding(rows).defaultName}
                aria-describedby={nameHintId}
                onChange={(event) => onNameDraftChange(event.target.value)}
              />
              <p id={nameHintId} className="project-grid-share-name-hint">
                Leave it blank to use the first line of your note.
              </p>
            </div>
            <div className="project-grid-share-note">
              <RichTextDetailEditor
                id="past-project-share-note"
                label="Curation note"
                labelHint="(shown at the top of the curation's page)"
                value={noteDraft}
                placeholder="Optional — add context for whoever opens the link."
                onChange={onNoteDraftChange}
              />
              <ProjectNoteInsertControl
                rows={rows}
                excludedFields={noteInsert.excludedFields}
                insertProblem={noteInsert.insertProblem}
                onInsert={() => noteInsert.insertRows(noteDraft, rows, onNoteDraftChange)}
                onToggleExcludedField={noteInsert.toggleField}
              />
            </div>
          </div>
          <div className="project-grid-share-actions">
            {saveButton}
            {pendingSaveCount > 0 ? (
              <p className="project-grid-share-pending" role="status">
                Waiting for projects to finish saving…
              </p>
            ) : (
              <span className="project-grid-share-actions-note">
                Saved curations are listed under My Curations, each with a link anyone can view.
              </span>
            )}
          </div>
        </>
      ) : (
        <p className="project-grid-share-login-hint">
          <SignInToSaveLink signIn={signIn}>Sign in</SignInToSaveLink>
          {signIn.inNewTab
            ? ' to sign in, save this curation and get a link to share it. This draft goes with you.'
            : ' to save this curation and get a link to share it.'}
        </p>
      )}
    </div>
  );
};
