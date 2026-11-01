import {useMemo, useState} from 'react';
import type {ProjectGridRow} from '../../grid/contracts/projectGrid';
import {appendPastProjectsNoteInsertHtml, type PastProjectNoteInsertField} from '../../richText/content/pastProjectsDetailText';
import {pluralize} from '../../shared/utils/saveResults';
import {NOTE_MAX_LENGTH, prepareNoteForSave} from './curationNote';

/**
 * "Insert Projects into Note": which project fields it leaves out, and the insert itself, which is refused when
 * the note would grow past what a curation can save. Shared by the builder and shared-page editors.
 */
export function useNoteInsertFields() {
  const [excludedFields, setExcludedFields] = useState<Set<PastProjectNoteInsertField>>(() => new Set());
  const [insertProblem, setInsertProblem] = useState('');
  const excludedFieldList = useMemo(() => Array.from(excludedFields), [excludedFields]);

  const toggleField = (field: PastProjectNoteInsertField) => {
    setInsertProblem('');
    setExcludedFields((current) => {
      const next = new Set(current);
      if (next.has(field)) {
        next.delete(field);
      } else {
        next.add(field);
      }
      return next;
    });
  };

  /** Append the rows to the note through `onNoteChange`, unless the note would then be too long to save. */
  const insertRows = (noteHtml: string, rows: ProjectGridRow[], onNoteChange: (html: string) => void) => {
    const nextHtml = appendPastProjectsNoteInsertHtml(noteHtml, rows, {excludedFields: excludedFieldList});
    if (prepareNoteForSave(nextHtml).length > NOTE_MAX_LENGTH) {
      setInsertProblem(
        `Inserting ${pluralize(rows.length, 'project')} would make the note longer than a curation can save ` +
          `(${NOTE_MAX_LENGTH.toLocaleString('en-US')} characters with formatting). Leave out Abstract under ` +
          'Choose Fields, or shorten the note.',
      );
      return;
    }
    setInsertProblem('');
    onNoteChange(nextHtml);
  };

  return {excludedFields, toggleField, insertProblem, insertRows};
}

export type NoteInsertFields = ReturnType<typeof useNoteInsertFields>;
