import {useState} from 'react';
import {useNavigate, useSearchParams} from 'react-router';
import {useAuth} from '@/features/auth';
import {
  type EventRegistrationOptions,
  type EventRegistrationSummary,
  type Registration,
} from '@/features/events/api';
import {type EventRegistrationStep} from '../../page/helpers';
import {useEventOptionsLoader} from './useEventOptionsLoader';
import {useRegistrationBoot} from './useRegistrationBoot';
import {useEventChoice} from './useEventChoice';

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
