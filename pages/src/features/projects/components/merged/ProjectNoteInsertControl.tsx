import {useId, useState} from 'react';
import type {ProjectGridRow} from '../projectGrid';
import {PAST_PROJECT_NOTE_INSERT_FIELDS, type PastProjectNoteInsertField} from '../richText/pastProjectsDetailText';

interface ProjectNoteInsertControlProps {
  rows: ProjectGridRow[];
  excludedFields: Set<PastProjectNoteInsertField>;
  onInsert: () => void;
  onToggleExcludedField: (field: PastProjectNoteInsertField) => void;
}

export const ProjectNoteInsertControl = ({
  rows,
  excludedFields,
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
          Insert projects into note
        </button>
        <button
          type="button"
          className="itg-btn itg-btn-text project-grid-note-insert-settings"
          aria-expanded={isOpen}
          aria-controls={isOpen ? menuId : undefined}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => setIsOpen((current) => !current)}
        >
          Choose fields
        </button>
      </div>
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
