import {useCallback, useRef, type Dispatch, type SetStateAction} from 'react';
import type {NavigateFunction} from 'react-router';
import {hasRequiredNameFields} from '@/features/auth/api/profileCompletion';
import {buildCompleteProfilePath} from '@/features/auth/api/redirects';
import {
  fetchRegistrationOptions,
  type EventRegistrationOptions,
  type EventRegistrationSummary,
  type Registration,
} from '@/features/events/api';
import {getRegistrationErrorMessage, type EventRegistrationStep} from '../steps/helpers';

export const registrationPathForEvent = (eventSlug?: string | null) =>
  eventSlug ? `/event-registration?event=${encodeURIComponent(eventSlug)}` : '/event-registration';

export const NOT_ACCEPTING = 'This event is not currently accepting registrations.';

/** What a failed member-options load shows: the sign-in step after a 401, else the error. */
const memberOptionsFailure = (err: unknown): {signIn: true} | {message: string} => {
  if ((err as {response?: {status?: number}}).response?.status === 401) {
    return {signIn: true};
  }
  const message = getRegistrationErrorMessage(err);
  return {message: message.toLowerCase().includes('accepting registrations') ? NOT_ACCEPTING : message};
};

interface UseEventOptionsLoaderOptions {
  navigate: NavigateFunction;
  setStep: (step: EventRegistrationStep) => void;
  setError: (message: string | null) => void;
  setEvents: Dispatch<SetStateAction<EventRegistrationSummary[]>>;
  setSelectedEventSlug: (slug: string) => void;
  setOptions: (options: EventRegistrationOptions | null) => void;
  setRegistration: (registration: Registration | null) => void;
  resetForm: () => void;
  invalidateContacts: () => void;
  prefillContacts: (data: EventRegistrationOptions) => void;
  prefillProfile: (data: EventRegistrationOptions) => void;
}

/**
 * Loading one event's options: the member's (routing on to done / form / profile completion) or the
 * public ones shown above the sign-in step. Only the latest request may touch state past its await.
 */
export function useEventOptionsLoader({
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
}: UseEventOptionsLoaderOptions) {
  // Guards against a superseded options fetch (rapid event switching) applying its state after
  // a newer request started; only the latest request may touch state past its await.
  const optionsRequestRef = useRef(0);

  const resetEventForm = useCallback(() => {
    setOptions(null);
    setRegistration(null);
    resetForm();
  }, [resetForm, setOptions, setRegistration]);

  // A changed contact or event invalidates every in-flight request.
  const invalidateRequests = useCallback(() => {
    optionsRequestRef.current += 1;
    invalidateContacts();
  }, [invalidateContacts]);

  const syncEventRegistration = useCallback(
    (eventSlug: string, nextRegistration: Registration | null) => {
      setEvents((current) =>
        current.map((event) => (event.slug === eventSlug ? {...event, registration: nextRegistration} : event)),
      );
    },
    [setEvents],
  );

  /** Start a request for an event's options; resolves to them, or to null when a newer request started meanwhile. */
  const fetchLatestOptions = useCallback(
    async (eventSlug: string) => {
      const requestId = ++optionsRequestRef.current;
      resetEventForm();
      setSelectedEventSlug(eventSlug);
      const data = await fetchRegistrationOptions(eventSlug);
      if (requestId !== optionsRequestRef.current) return null;
      setOptions(data);
      syncEventRegistration(data.slug, data.registration);
      return data;
    },
    [resetEventForm, setOptions, setSelectedEventSlug, syncEventRegistration],
  );

  /** Route a member's loaded options to the done step, profile completion, or the form. */
  const routeMemberOptions = useCallback(
    (data: EventRegistrationOptions) => {
      if (data.registration) {
        setRegistration(data.registration);
        setStep('done');
        return;
      }
      prefillContacts(data);
      if (data.member_profile && !hasRequiredNameFields(data.member_profile)) {
        navigate(buildCompleteProfilePath(registrationPathForEvent(data.slug)), {replace: true});
        return;
      }
      prefillProfile(data);
      setStep('form');
    },
    [navigate, prefillContacts, prefillProfile, setRegistration, setStep],
  );

  /** Load the signed-in member's options for an event and route to the done/form/profile step. */
  const loadOptionsAndRoute = useCallback(
    async (eventSlug: string, fallbackToEventList = false) => {
      // fetchLatestOptions takes the next request number synchronously, before its first await.
      const requestId = optionsRequestRef.current + 1;
      try {
        const data = await fetchLatestOptions(eventSlug);
        if (data) routeMemberOptions(data);
      } catch (err: unknown) {
        if (requestId !== optionsRequestRef.current) return;
        const failure = memberOptionsFailure(err);
        if ('signIn' in failure) {
          setStep('email');
          return;
        }
        setError(failure.message);
        setStep(fallbackToEventList ? 'select' : 'loading');
      }
    },
    [fetchLatestOptions, routeMemberOptions, setError, setStep],
  );

  /** A visitor who is not signed in sees the event's public details above the sign-in step. */
  const loadPublicOptionsForEmailStep = useCallback(
    async (eventSlug: string) => {
      const requestId = optionsRequestRef.current + 1;
      try {
        const data = await fetchLatestOptions(eventSlug);
        if (data) setStep('email');
      } catch (err: unknown) {
        if (requestId !== optionsRequestRef.current) return;
        setError(getRegistrationErrorMessage(err));
        setStep('email');
      }
    },
    [fetchLatestOptions, setError, setStep],
  );

  return {invalidateRequests, syncEventRegistration, loadOptionsAndRoute, loadPublicOptionsForEmailStep};
}
