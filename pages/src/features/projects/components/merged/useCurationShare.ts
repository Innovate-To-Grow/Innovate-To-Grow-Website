import {useEffect, useRef, useState} from 'react';
import type {ProjectGridRow} from '../projectGrid';
import {getShareErrorMessage} from '../shareHelpers';
import {prepareNoteForSave} from './curationNote';

/** Mirrors the backend serializer, which rejects a curation with more rows. */
const MAX_CURATION_ROWS = 1000;

export type PastProjectShareCreationResult =
  | string
  | {
      id: string;
      share_url?: string;
    };

interface UseCurationShareOptions {
  onCreateShare?: (rows: ProjectGridRow[], name: string, note: string) => Promise<PastProjectShareCreationResult>;
  /** The rows the builder's search shows: a curation is saved from exactly these. */
  visibleRows: ProjectGridRow[];
  /** Saves still loading their projects; saving waits, or the curation would leave those rows out. */
  pendingSaveCount: number;
  /** The builder's unsaved curation name and note. Left out, the card keeps them itself. */
  nameDraft?: string;
  noteDraft?: string;
  onNameDraftChange?: (name: string) => void;
  onNoteDraftChange?: (note: string) => void;
  onStatus: (message: string) => void;
}

/** Saving the builder's merged rows as a new curation (a shared page). */
export function useCurationShare({
  onCreateShare,
  visibleRows,
  pendingSaveCount,
  nameDraft: controlledNameDraft,
  noteDraft: controlledNoteDraft,
  onNameDraftChange,
  onNoteDraftChange,
  onStatus,
}: UseCurationShareOptions) {
  const [isSharing, setIsSharing] = useState(false);
  const [localNameDraft, setLocalNameDraft] = useState('');
  const [localNoteDraft, setLocalNoteDraft] = useState('');
  const isMountedRef = useRef(true);
  const nameDraft = controlledNameDraft ?? localNameDraft;
  const noteDraft = controlledNoteDraft ?? localNoteDraft;
  const setNameDraft = onNameDraftChange ?? setLocalNameDraft;
  const setNoteDraft = onNoteDraftChange ?? setLocalNoteDraft;

  useEffect(() => {
    // Set in the body too: StrictMode runs this cleanup once on mount, which would leave it false.
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const createShare = async () => {
    // The name is optional — when blank the backend derives one from the curation content. Only rows are required.
    if (!onCreateShare || !visibleRows.length || pendingSaveCount > 0) {
      return;
    }
    if (visibleRows.length > MAX_CURATION_ROWS) {
      onStatus('A curation can include at most 1000 projects. Remove some rows and try again.');
      return;
    }

    setIsSharing(true);
    onStatus('');
    try {
      await onCreateShare(visibleRows, nameDraft.trim(), prepareNoteForSave(noteDraft));
      if (isMountedRef.current) {
        onStatus('Saved. Opening your curation...');
      }
    } catch (error) {
      if (isMountedRef.current) {
        onStatus(getShareErrorMessage(error));
      }
    } finally {
      if (isMountedRef.current) {
        setIsSharing(false);
      }
    }
  };

  return {nameDraft, noteDraft, setNameDraft, setNoteDraft, isSharing, createShare};
}
