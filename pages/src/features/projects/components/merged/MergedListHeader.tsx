import type {ReactNode, RefObject} from 'react';
import {pluralize} from '../saveResults';
import {SharedEditIcon, SharedSaveIcon} from '../richText/shareEditorIcons';
import {currentLoginPath, formatSharedDate} from './curationNote';
import type {SharedListEditor} from './useSharedListEditor';

interface SharedListHeaderProps {
  headingId: string;
  title: string;
  rowCount: number;
  sharedAt?: string;
  /** Present when the viewer may rename the list. */
  editor: SharedListEditor | null;
  titleInputRef: RefObject<HTMLInputElement | null>;
}

export const SharedListHeader = ({headingId, title, rowCount, sharedAt, editor, titleInputRef}: SharedListHeaderProps) => {
  const sharedDate = formatSharedDate(sharedAt);
  const isEditing = Boolean(editor?.isEditingTitle);

  return (
    <header className="project-grid-shared-header">
      <p className="itg-eyebrow">Shared list · Past Projects</p>
      <div className={`project-grid-share-title-editor${isEditing ? ' is-editing' : ''}`}>
        {editor && isEditing ? (
          <input
            ref={titleInputRef}
            type="text"
            className="itg-input project-grid-share-title-input"
            aria-label="Shared page name"
            value={editor.titleDraft}
            maxLength={200}
            onChange={(event) => editor.setTitleDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                void editor.titleAction();
              }
            }}
          />
        ) : (
          <h1 id={headingId} className="itg-page-title project-grid-card-title" tabIndex={-1}>
            {title}
          </h1>
        )}
        {editor ? (
          <button
            type="button"
            className={`itg-btn itg-btn-text project-grid-share-editor-icon-button project-grid-share-title-action${
              isEditing ? ' is-active' : ''
            }`}
            onClick={() => void editor.titleAction()}
            disabled={editor.isSaving}
          >
            {isEditing ? <SharedSaveIcon /> : <SharedEditIcon />}
            {isEditing ? 'Save name' : 'Edit name'}
          </button>
        ) : null}
      </div>
      <p className="itg-page-meta">
        {pluralize(rowCount, 'project')}
        {sharedDate ? ` · shared ${sharedDate}` : ''}
      </p>
    </header>
  );
};

interface BuilderCardHeaderProps {
  headingId: string;
  title: string;
  rowCount: number;
  /** Whether this card can be saved as a curation at all. */
  canSave: boolean;
  isAuthenticated: boolean;
  saveButton: ReactNode;
}

export const BuilderCardHeader = ({
  headingId,
  title,
  rowCount,
  canSave,
  isAuthenticated,
  saveButton,
}: BuilderCardHeaderProps) => (
  <div className="project-grid-card-header">
    <div className="project-grid-card-heading">
      <h2 id={headingId} className="project-grid-card-title" tabIndex={-1}>
        {title}
      </h2>
      <p className="project-grid-card-count">
        <strong>{pluralize(rowCount, 'project')}</strong> in this list
      </p>
    </div>
    {canSave ? (
      <div className="project-grid-save-status">
        {isAuthenticated ? saveButton : (
          <a className="itg-btn itg-btn-primary" href={currentLoginPath()}>
            Sign in to save
          </a>
        )}
        <p className="project-grid-draft-note">Not saved yet. This browser keeps the list until you save it.</p>
      </div>
    ) : null}
  </div>
);
