import {useEffect, useRef, useState} from 'react';
import type {ProjectGridItem, ProjectGridRow} from '../projectGrid';
import {prepareNoteForSave} from './curationNote';

interface UseSharedListEditorOptions {
  /** Every saved row, as the shared page stores them. */
  rows: ProjectGridItem[];
  allRows: ProjectGridRow[];
  title: string;
  note?: string;
  onUpdateShare?: (rows: ProjectGridRow[], name: string, note: string) => Promise<void>;
  onStatus: (message: string) => void;
}

/**
 * A draft of a saved value with its inline editor. A change of the saved value resets the draft and
 * closes the editor — done during render (React's documented "adjusting state on prop change" pattern)
 * rather than in an effect, avoiding the extra commit a synchronous setState in an effect would cause.
 */
function useSyncedDraft(saved: string) {
  const [draft, setDraft] = useState(saved);
  const [isEditing, setIsEditing] = useState(false);
  const [lastSynced, setLastSynced] = useState(saved);
  if (lastSynced !== saved) {
    setLastSynced(saved);
    setDraft(saved);
    setIsEditing(false);
  }
  return {draft, setDraft, isEditing, setIsEditing};
}

/** Write the whole list (rows, name, note); reports the outcome and resolves to whether it saved. */
function useShareSave(onUpdateShare: UseSharedListEditorOptions['onUpdateShare'], onStatus: (message: string) => void) {
  const [isSaving, setIsSaving] = useState(false);
  const save = async (nextRows: ProjectGridRow[], nextName: string, nextNote: string, successMessage: string) => {
    if (!onUpdateShare) {
      return false;
    }

    setIsSaving(true);
    onStatus('');
    try {
      await onUpdateShare(nextRows, nextName, nextNote);
      onStatus(successMessage);
      return true;
    } catch {
      onStatus('Unable to update this shared page. Please try again.');
      return false;
    } finally {
      setIsSaving(false);
    }
  };
  return {isSaving, save};
}

/**
 * Editing a saved shared list in place: its name, its note, removing rows (with a one-step undo).
 * Every write sends the whole list, so each save is the full snapshot plus one change.
 */
export function useSharedListEditor({rows, allRows, title, note, onUpdateShare, onStatus}: UseSharedListEditorOptions) {
  const savedNote = note ?? '';
  const {draft: titleDraft, setDraft: setTitleDraft, isEditing: isEditingTitle, setIsEditing: setIsEditingTitle} =
    useSyncedDraft(title);
  const {draft: noteDraft, setDraft: setNoteDraft, isEditing: isEditingNote, setIsEditing: setIsEditingNote} =
    useSyncedDraft(savedNote);
  const {isSaving, save} = useShareSave(onUpdateShare, onStatus);
  const [rowsUndo, setRowsUndo] = useState<ProjectGridRow[] | null>(null);
  const titleInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditingTitle) {
      titleInputRef.current?.focus();
      titleInputRef.current?.select();
    }
  }, [isEditingTitle]);

  const hasTitleChanges = titleDraft.trim() !== title.trim();
  // Compare both sides through prepareNoteForSave — the exact normalization used for the write —
  // so a no-op edit (the editor re-emits normalized markup) or emptying a note to residual markup
  // ('<br>', '<div></div>') is not mistaken for a change and does not fire a no-op save.
  const hasNoteChanges = prepareNoteForSave(noteDraft) !== prepareNoteForSave(savedNote);

  /** First click opens the name editor; the second saves it (or just closes it when unchanged). */
  const titleAction = async () => {
    if (!isEditingTitle) {
      setIsEditingTitle(true);
      setIsEditingNote(false);
      return;
    }
    if (!hasTitleChanges) {
      setIsEditingTitle(false);
      return;
    }
    if (await save(allRows, titleDraft.trim(), savedNote, 'Name updated.')) {
      setIsEditingTitle(false);
    }
  };

  const noteAction = async () => {
    if (!isEditingNote) {
      setIsEditingNote(true);
      setIsEditingTitle(false);
      return;
    }
    if (!hasNoteChanges) {
      setIsEditingNote(false);
      return;
    }
    if (await save(allRows, title, prepareNoteForSave(noteDraft), 'Note updated.')) {
      setIsEditingNote(false);
    }
  };

  const deleteRow = async (row: ProjectGridItem) => {
    const rowIndex = rows.findIndex((candidate) => candidate.__key === row.__key);
    if (rowIndex < 0) {
      return;
    }
    const nextRows = allRows.filter((_, index) => index !== rowIndex);
    if (!nextRows.length) {
      onStatus('A shared page needs at least one project.');
      return;
    }
    if (await save(nextRows, title, savedNote, 'Project removed.')) {
      setRowsUndo(allRows);
    }
  };

  const undoRows = async () => {
    if (!rowsUndo) {
      return;
    }
    if (await save(rowsUndo, title, savedNote, 'Change undone.')) {
      setRowsUndo(null);
    }
  };

  return {
    titleDraft,
    setTitleDraft,
    noteDraft,
    setNoteDraft,
    isSaving,
    isEditingTitle,
    isEditingNote,
    canUndo: Boolean(rowsUndo),
    titleInputRef,
    titleAction,
    noteAction,
    deleteRow,
    undoRows,
  };
}

/** The editor state and actions, without the title input's ref (pass that to the input separately). */
export type SharedListEditor = Omit<ReturnType<typeof useSharedListEditor>, 'titleInputRef'>;
