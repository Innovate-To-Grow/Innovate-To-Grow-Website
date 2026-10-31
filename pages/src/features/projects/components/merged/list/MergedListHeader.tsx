import type {ReactNode, RefObject} from 'react';
import {pluralize} from '../../shared/utils/saveResults';
import {SharedEditIcon, SharedSaveIcon} from '../../richText/editor/shareEditorIcons';
import {formatSharedDate, type SignInToSave} from './curationNote';
import {SignInToSaveLink} from './SignInToSaveLink';
import type {SharedListEditor} from '../shared/useSharedListEditor';

interface SharedListHeaderProps {
  headingId: string;
  /** Over the name: which list the projects come from (curationBranding). */
  eyebrow: string;
  title: string;
  rowCount: number;
  sharedAt?: string;
  /** Present when the viewer may rename the list. */
  editor: SharedListEditor | null;
  titleInputRef: RefObject<HTMLInputElement | null>;
}

export const SharedListHeader = ({
  headingId,
  eyebrow,
  title,
  rowCount,
  sharedAt,
  editor,
  titleInputRef,
}: SharedListHeaderProps) => {
  const sharedDate = formatSharedDate(sharedAt);
  const isEditing = Boolean(editor?.isEditingTitle);

  return (
    <header className="project-grid-shared-header">
      <p className="itg-eyebrow">{eyebrow}</p>
      <div className={`project-grid-share-title-editor${isEditing ? ' is-editing' : ''}`}>
        {editor && isEditing ? (
          <input
            ref={titleInputRef}
            type="text"
            className="itg-input project-grid-share-title-input"
            aria-label="Curation name"
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
      {/* The name and note are a member's own words on the site's domain: say who put the page together. */}
      <p className="itg-page-meta">
        Curated by a site member · {pluralize(rowCount, 'project')}
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
  signIn: SignInToSave;
}

export const BuilderCardHeader = ({
  headingId,
  title,
  rowCount,
  canSave,
  isAuthenticated,
  saveButton,
  signIn,
}: BuilderCardHeaderProps) => (
  <div className="project-grid-card-header">
    <div className="project-grid-card-heading">
      <h2 id={headingId} className="project-grid-card-title" tabIndex={-1}>
        {title}
      </h2>
      <p className="project-grid-card-count">
        <strong>{pluralize(rowCount, 'project')}</strong> in this draft
      </p>
    </div>
    {canSave ? (
      <div className="project-grid-save-status">
        {isAuthenticated ? (
          saveButton
        ) : (
          <SignInToSaveLink className="itg-btn itg-btn-primary" signIn={signIn}>
            Sign in to save
          </SignInToSaveLink>
        )}
        <p className="project-grid-draft-note">Not saved yet. This browser keeps the draft until you save it.</p>
      </div>
    ) : null}
  </div>
);
