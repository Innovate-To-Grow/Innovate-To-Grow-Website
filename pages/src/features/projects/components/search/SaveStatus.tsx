import {PastProjectsAIStatus} from '../builder/PastProjectsAIStatus';
import {pluralize} from '../saveResults';
import type {SaveProgress, SearchTableSaveResult} from './types';

interface SaveStatusProps {
  saveProgress: SaveProgress | null;
  saveStatus: SearchTableSaveResult | null;
  mergingVerb: string;
}

const progressMessage = (saveProgress: SaveProgress | null, mergingVerb: string) =>
  saveProgress ? `${mergingVerb} ${pluralize(saveProgress.count, 'project')}…` : '';

// Screen readers hear outcomes apart from the visible box, so an outcome is announced wherever (or whether)
// that box is shown: a persistent polite region, and for errors an alert, which is announced when it appears.
export const SaveStatusAnnouncer = ({saveProgress, saveStatus, mergingVerb}: SaveStatusProps) => {
  const progressText = progressMessage(saveProgress, mergingVerb);
  const politeText = progressText || (saveStatus && saveStatus.tone !== 'error' ? saveStatus.message : '');
  const alertText = !saveProgress && saveStatus?.tone === 'error' ? saveStatus.message : '';
  return (
    <>
      <p className="sr-only" role="status" aria-live="polite">
        {politeText}
      </p>
      {alertText ? (
        <p className="sr-only" role="alert">
          {alertText}
        </p>
      ) : null}
    </>
  );
};

interface VisibleSaveStatusProps extends SaveStatusProps {
  viewMergedResultsLabel: string;
  onViewMergedResults?: () => void;
}

/** The visible progress or outcome, without its own live region (SaveStatusAnnouncer speaks it). */
export const VisibleSaveStatus = ({
  saveProgress,
  saveStatus,
  mergingVerb,
  viewMergedResultsLabel,
  onViewMergedResults,
}: VisibleSaveStatusProps) => {
  if (saveProgress) {
    // Counts settled requests, failed ones included, so it reports progress rather than how many loaded.
    const loading = saveProgress.total ? ` Loading details: ${saveProgress.done} of ${saveProgress.total}.` : '';
    return (
      <PastProjectsAIStatus
        announce={false}
        tone="loading"
        message={`${progressMessage(saveProgress, mergingVerb)}${loading}`}
      />
    );
  }
  if (!saveStatus) {
    return null;
  }
  return (
    <>
      <PastProjectsAIStatus announce={false} tone={saveStatus.tone} message={saveStatus.message} />
      {onViewMergedResults && saveStatus.tone !== 'error' ? (
        <button type="button" className="itg-btn itg-btn-text past-projects-status-action" onClick={onViewMergedResults}>
          {viewMergedResultsLabel}
        </button>
      ) : null}
    </>
  );
};
