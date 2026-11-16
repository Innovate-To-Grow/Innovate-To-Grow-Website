import {type EventRegistrationOptions, type Registration} from '@/features/events/api';
import {type EventRegistrationStep} from '../../page/helpers';

interface UseEventChoiceOptions {
  searchParams: URLSearchParams;
  setSearchParams: (params: URLSearchParams) => void;
  invalidateRequests: () => void;
  setError: (message: string | null) => void;
  setOptions: (options: EventRegistrationOptions | null) => void;
  setRegistration: (registration: Registration | null) => void;
  setSelectedEventSlug: (slug: string) => void;
  setStep: (step: EventRegistrationStep) => void;
  hasEvents: boolean;
}

/** Choosing an event, and going back to the list of open events. */
export function useEventChoice({
  searchParams,
  setSearchParams,
  invalidateRequests,
  setError,
  setOptions,
  setRegistration,
  setSelectedEventSlug,
  setStep,
  hasEvents,
}: UseEventChoiceOptions) {
  // Selection updates only the query string (never the pathname) so it works identically on
  // /event-registration and inside the chromeless /_embed/:embedSlug iframe; copying the current
  // params preserves the embed's hide-titles/hide-sections flags. Boot re-runs via eventSlugParam.
  const handleSelectEvent = (eventSlug: string) => {
    invalidateRequests();
    setError(null);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('event', eventSlug);
    setSearchParams(nextParams);
  };

  const handleShowEventList = () => {
    invalidateRequests();
    setError(null);
    setOptions(null);
    setRegistration(null);
    setSelectedEventSlug('');
    setStep(hasEvents ? 'select' : 'loading');
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('event');
    setSearchParams(nextParams);
  };

  return {handleSelectEvent, handleShowEventList};
}
