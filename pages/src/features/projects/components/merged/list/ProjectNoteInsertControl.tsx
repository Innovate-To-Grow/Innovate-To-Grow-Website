import {useId, useState} from 'react';
import type {ProjectGridRow} from '../../grid/contracts/projectGrid';
import {PAST_PROJECT_NOTE_INSERT_FIELDS, type PastProjectNoteInsertField} from '../../richText/content/pastProjectsDetailText';

interface ProjectNoteInsertControlProps {
  rows: ProjectGridRow[];
  excludedFields: Set<PastProjectNoteInsertField>;
  /** Why the last insert was refused (the note would be too long to save). */
  insertProblem?: string;
  onInsert: () => void;
  onToggleExcludedField: (field: PastProjectNoteInsertField) => void;
}

export const ProjectNoteInsertControl = ({
  rows,
  excludedFields,
  insertProblem,
  onInsert,
  onToggleExcludedField,
}: ProjectNoteInsertControlProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const menuId = useId();

  return (
    <div
      className={`project-grid-note-insert-control${isOpen ? ' is-open' : ''}`}
      role="group"
      aria-label="Note insert tools"
    >
      <div className="project-grid-note-insert-actions">
        <button type="button" className="itg-btn itg-btn-text" onClick={onInsert} disabled={!rows.length}>
          Insert Projects into Note
        </button>
        <button
          type="button"
          className="itg-btn itg-btn-text project-grid-note-insert-settings"
          aria-expanded={isOpen}
          aria-controls={isOpen ? menuId : undefined}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => setIsOpen((current) => !current)}
        >
          Choose Fields
        </button>
      </div>
      {insertProblem ? (
        <p className="project-grid-note-insert-problem itg-error" role="alert">
          {insertProblem}
        </p>
      ) : null}
      {isOpen ? (
        <fieldset id={menuId} className="project-grid-note-insert-menu">
          <legend className="project-grid-note-insert-menu-title">Leave these fields out</legend>
          {PAST_PROJECT_NOTE_INSERT_FIELDS.map((field) => (
            <label key={field.key} className="project-grid-note-insert-option">
              <input
                type="checkbox"
                checked={excludedFields.has(field.key)}
                onChange={() => onToggleExcludedField(field.key)}
              />
              <span>{field.label}</span>
            </label>
          ))}
        </fieldset>
      ) : null}
    </div>
  );
};
