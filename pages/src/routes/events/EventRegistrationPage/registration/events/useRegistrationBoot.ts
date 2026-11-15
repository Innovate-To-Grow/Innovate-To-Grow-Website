import {useEffect} from 'react';
import {type NavigateFunction} from 'react-router';
import {buildCompleteProfilePath} from '@/features/auth/api/navigation/redirects';
import {
  fetchRegistrationEvents,
  type EventRegistrationOptions,
  type EventRegistrationSummary,
  type Registration,
} from '@/features/events/api';
import {getRegistrationErrorMessage, type EventRegistrationStep} from '../../page/helpers';
import {NOT_ACCEPTING, registrationPathForEvent} from './useEventOptionsLoader';

/** The event to open on boot: the linked one, else the only open event; '' shows the event list. */
const bootEventSlug = (eventList: EventRegistrationSummary[], eventSlugParam: string) =>
  eventSlugParam || (eventList.length === 1 ? eventList[0].slug : '');

interface UseRegistrationBootOptions {
  isAuthenticated: boolean;
  requiresProfileCompletion: boolean;
  eventSlugParam: string;
  navigate: NavigateFunction;
  setError: (message: string | null) => void;
  setStep: (step: EventRegistrationStep) => void;
  setEvents: (events: EventRegistrationSummary[]) => void;
  setSelectedEventSlug: (slug: string) => void;
  setOptions: (options: EventRegistrationOptions | null) => void;
  setRegistration: (registration: Registration | null) => void;
  loadOptionsAndRoute: (eventSlug: string, fallbackToEventList?: boolean) => Promise<void>;
  loadPublicOptionsForEmailStep: (eventSlug: string) => Promise<void>;
  invalidateRequests: () => void;
}

/**
 * On mount and whenever the linked event or the sign-in changes: load the open events and open the linked
 * (or only) one, else show the list; a member who must complete their profile goes there first.
 */
export function useRegistrationBoot({
  isAuthenticated,
  requiresProfileCompletion,
  eventSlugParam,
  navigate,
  setError,
  setStep,
  setEvents,
  setSelectedEventSlug,
  setOptions,
  setRegistration,
  loadOptionsAndRoute,
  loadPublicOptionsForEmailStep,
  invalidateRequests,
}: UseRegistrationBootOptions) {
  useEffect(() => {
    const profileCompletionPathForQueryEvent = buildCompleteProfilePath(registrationPathForEvent(eventSlugParam));
    if (isAuthenticated && requiresProfileCompletion) {
      navigate(profileCompletionPathForQueryEvent, {replace: true});
      return;
    }

    let cancelled = false;
    const showEventList = (message: string | null) => {
      setSelectedEventSlug('');
      setOptions(null);
      setRegistration(null);
      if (message) setError(message);
      setStep('select');
    };
    const boot = async () => {
      setStep('loading');
      setError(null);
      try {
        const eventList = await fetchRegistrationEvents();
        if (cancelled) return;
        setEvents(eventList);
        if (eventList.length === 0) {
          setSelectedEventSlug('');
          setOptions(null);
          setError('No event is currently accepting registrations.');
          setStep('loading');
          return;
        }
        const nextSlug = bootEventSlug(eventList, eventSlugParam);
        if (!nextSlug) {
          showEventList(null);
        } else if (!eventList.some((event) => event.slug === nextSlug)) {
          // Recover onto the event list (even with a single open event) instead of a dead end.
          showEventList(NOT_ACCEPTING);
        } else if (isAuthenticated) {
          await loadOptionsAndRoute(nextSlug, true);
        } else {
          await loadPublicOptionsForEmailStep(nextSlug);
        }
      } catch (err: unknown) {
        if (cancelled) return;
        setError(getRegistrationErrorMessage(err));
        setStep('loading');
      }
    };

    void boot();
    return () => {
      cancelled = true;
      invalidateRequests();
    };
  }, [
    eventSlugParam,
    invalidateRequests,
    isAuthenticated,
    loadOptionsAndRoute,
    loadPublicOptionsForEmailStep,
    navigate,
    requiresProfileCompletion,
    setError,
    setEvents,
    setOptions,
    setRegistration,
    setSelectedEventSlug,
    setStep,
  ]);
}
