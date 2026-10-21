// Wording for the outcome of saving a search table's checked rows, shared by the builder (Save Selected) and
// the shared page (Add Selected).
import type {SearchTableSaveResult} from './SearchTableCard';

export const pluralize = (count: number, noun: string) => `${count} ${noun}${count === 1 ? '' : 's'}`;

interface SaveCounts {
  added: number;
  alreadySaved: number;
  failed: number;
  unavailable: number;
}

interface SaveWording {
  /** Follows "N projects", e.g. "added to Saved Merged Results (12 in total)." */
  added: string;
  /** Follows "N projects were already", next to other outcomes, e.g. "saved". */
  already: string;
  /** Where saved projects live, when that is the whole outcome, e.g. "in Saved Merged Results". */
  place: string;
  /** The button that saves, e.g. "Save Selected". */
  retryLabel: string;
}

const wasWere = (count: number) => (count === 1 ? 'was' : 'were');
const isAre = (count: number) => (count === 1 ? 'is' : 'are');

const alreadySavedSentence = ({added, alreadySaved, failed, unavailable}: SaveCounts, wording: SaveWording) =>
  added || failed || unavailable
    ? `${pluralize(alreadySaved, 'project')} ${wasWere(alreadySaved)} already ${wording.already}.`
    : `${alreadySaved === 1 ? 'That project is' : 'Those projects are'} already ${wording.place}.`;

const saveTone = ({added, failed, unavailable}: SaveCounts): SearchTableSaveResult['tone'] => {
  if (failed || (unavailable && !added)) return 'error';
  return added ? 'success' : 'info';
};

export const describeSaveResult = (
  counts: SaveCounts,
  wording: SaveWording,
): Pick<SearchTableSaveResult, 'tone' | 'message'> => {
  const {added, alreadySaved, failed, unavailable} = counts;
  const parts: string[] = [];
  if (added) {
    parts.push(`${pluralize(added, 'project')} ${wording.added}`);
  }
  if (alreadySaved) {
    parts.push(alreadySavedSentence(counts, wording));
  }
  if (unavailable) {
    parts.push(
      `${pluralize(unavailable, 'project')} ${isAre(unavailable)} no longer in the archive ` +
        `and ${wasWere(unavailable)} skipped.`,
    );
  }
  if (failed) {
    parts.push(
      `${pluralize(failed, 'project')} could not be loaded and ${isAre(failed)} still selected. ` +
        `Click ${wording.retryLabel} to try again.`,
    );
  }
  return {tone: saveTone(counts), message: parts.join(' ')};
};
