import {useMemo, useState} from 'react';
import type {ProjectGridRow} from '../projectGrid';
import {appendPastProjectsNoteInsertHtml, type PastProjectNoteInsertField} from '../richText/pastProjectsDetailText';

/** Which project fields "Insert projects into note" leaves out; shared by the builder and shared-page editors. */
export function useNoteInsertFields() {
  const [excludedFields, setExcludedFields] = useState<Set<PastProjectNoteInsertField>>(() => new Set());
  const excludedFieldList = useMemo(() => Array.from(excludedFields), [excludedFields]);

  const toggleField = (field: PastProjectNoteInsertField) => {
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

  const appendRows = (noteHtml: string, rows: ProjectGridRow[]) =>
    appendPastProjectsNoteInsertHtml(noteHtml, rows, {excludedFields: excludedFieldList});

  return {excludedFields, toggleField, appendRows};
}

export type NoteInsertFields = ReturnType<typeof useNoteInsertFields>;
