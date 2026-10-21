import {useEffect, useState} from 'react';
import {useNavigate, useSearchParams, type NavigateFunction} from 'react-router';
import {useAuth} from '@/features/auth';
import {buildCompleteProfilePath} from '@/features/auth/api/redirects';
import {
  fetchRegistrationEvents,
  type EventRegistrationOptions,
  type EventRegistrationSummary,
  type Registration,
} from '@/features/events/api';
import {getRegistrationErrorMessage, type EventRegistrationStep} from '../steps/helpers';
import {NOT_ACCEPTING, registrationPathForEvent, useEventOptionsLoader} from './useEventOptionsLoader';

/** The event to open on boot: the linked one, else the only open event; '' shows the event list. */
const bootEventSlug = (eventList: EventRegistrationSummary[], eventSlugParam: string) =>
  eventSlugParam || (eventList.length === 1 ? eventList[0].slug : '');

interface UseRegistrationEventsOptions {
  setError: (message: string | null) => void;
  /** Clear every per-event form field (a different event, or the same one reloaded). */
  resetForm: () => void;
  /** Bump the contact verifications' request numbers so no in-flight response lands. */
  invalidateContacts: () => void;
  /** Prefill the contact fields from a signed-in member's options. */
  prefillContacts: (data: EventRegistrationOptions) => void;
  /** Prefill the attendee profile (only once the profile is known to be complete). */
  prefillProfile: (data: EventRegistrationOptions) => void;
}

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
function useRegistrationBoot({
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
function useEventChoice({
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

/**
 * Which event is being registered for and which step shows: the open events, the chosen event's
 * options (public before sign-in, the member's after), and the routing between steps. The `event`
 * query parameter is the source of truth for the chosen event.
 */
export function useRegistrationEvents({
  setError,
  resetForm,
  invalidateContacts,
  prefillContacts,
  prefillProfile,
}: UseRegistrationEventsOptions) {
  const {isAuthenticated, requiresProfileCompletion} = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const eventSlugParam = searchParams.get('event') || '';
  const [step, setStep] = useState<EventRegistrationStep>('loading');
  const [events, setEvents] = useState<EventRegistrationSummary[]>([]);
  const [selectedEventSlug, setSelectedEventSlug] = useState(eventSlugParam);
  const [options, setOptions] = useState<EventRegistrationOptions | null>(null);
  const [registration, setRegistration] = useState<Registration | null>(null);
  const {invalidateRequests, syncEventRegistration, loadOptionsAndRoute, loadPublicOptionsForEmailStep} =
    useEventOptionsLoader({
      navigate,
      setStep,
      setError,
      setEvents,
      setSelectedEventSlug,
      setOptions,
      setRegistration,
      resetForm,
      invalidateContacts,
      prefillContacts,
      prefillProfile,
    });

  useRegistrationBoot({
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
  });

  const {handleSelectEvent, handleShowEventList} = useEventChoice({
    searchParams,
    setSearchParams,
    invalidateRequests,
    setError,
    setOptions,
    setRegistration,
    setSelectedEventSlug,
    setStep,
    hasEvents: events.length > 0,
  });

  /** The event the visitor is registering for, chosen or from the link. */
  const currentEventSlug = selectedEventSlug || eventSlugParam;

  return {
    step,
    setStep,
    events,
    selectedEventSlug,
    currentEventSlug,
    options,
    registration,
    setRegistration,
    syncEventRegistration,
    loadOptionsAndRoute,
    handleSelectEvent,
    handleShowEventList,
  };
}
