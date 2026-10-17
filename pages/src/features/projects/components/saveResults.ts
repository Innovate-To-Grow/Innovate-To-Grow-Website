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

export const describeSaveResult = (
  {added, alreadySaved, failed, unavailable}: SaveCounts,
  {added: addedText, already, place, retryLabel}: SaveWording,
): Pick<SearchTableSaveResult, 'tone' | 'message'> => {
  const parts: string[] = [];
  if (added) {
    parts.push(`${pluralize(added, 'project')} ${addedText}`);
  }
  if (alreadySaved) {
    parts.push(
      added || failed || unavailable
        ? `${pluralize(alreadySaved, 'project')} ${alreadySaved === 1 ? 'was' : 'were'} already ${already}.`
        : `${alreadySaved === 1 ? 'That project is' : 'Those projects are'} already ${place}.`,
    );
  }
  if (unavailable) {
    parts.push(
      `${pluralize(unavailable, 'project')} ${unavailable === 1 ? 'is' : 'are'} no longer in the archive ` +
        `and ${unavailable === 1 ? 'was' : 'were'} skipped.`,
    );
  }
  if (failed) {
    parts.push(
      `${pluralize(failed, 'project')} could not be loaded and ${failed === 1 ? 'is' : 'are'} still selected. ` +
        `Click ${retryLabel} to try again.`,
    );
  }
  return {tone: failed || (unavailable && !added) ? 'error' : added ? 'success' : 'info', message: parts.join(' ')};
};
