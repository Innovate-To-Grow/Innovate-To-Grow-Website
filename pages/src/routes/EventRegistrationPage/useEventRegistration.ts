import {useCallback, useEffect, useMemo, useRef, useState, type FormEvent} from 'react';
import {useNavigate, useSearchParams} from 'react-router-dom';
import {useAuth} from '@/features/auth';
import {updateProfileFields} from '@/features/auth';
import {
  createRegistration,
  fetchRegistrationEvents,
  fetchRegistrationOptions,
  sendPhoneCode,
  verifyPhoneCode,
  type EventRegistrationOptions,
  type EventRegistrationSummary,
  type Registration,
} from '@/features/events/api';
import {maxPhoneDigits, validatePhoneDigits} from '@/lib/phoneRegions';
import {hasRequiredNameFields} from '@/features/auth/api/profileCompletion';
import {buildCompleteProfilePath} from '@/features/auth/api/redirects';
import {identifyLoginInput} from '@/features/auth/components/sections/internal/identifyLoginInput';
import {getRegistrationErrorMessage, type EventRegistrationStep} from './steps/helpers';

export type OrganizationType = 'individual' | 'organization';

const registrationPathForEvent = (eventSlug?: string | null) =>
  eventSlug ? `/event-registration?event=${encodeURIComponent(eventSlug)}` : '/event-registration';

export const useEventRegistration = () => {
  const {
    isAuthenticated,
    requiresProfileCompletion,
    requestEmailAuthCode,
    verifyEmailAuthCode,
    requestPhoneAuthCode,
    verifyPhoneAuthCode,
  } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const eventSlugParam = searchParams.get('event') || '';
  const [step, setStep] = useState<EventRegistrationStep>('loading');
  const [events, setEvents] = useState<EventRegistrationSummary[]>([]);
  const [selectedEventSlug, setSelectedEventSlug] = useState(eventSlugParam);
  const [options, setOptions] = useState<EventRegistrationOptions | null>(null);
  const [registration, setRegistration] = useState<Registration | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [identifierType, setIdentifierType] = useState<'email' | 'phone'>('email');
  // Canonical value sent to the verify call: a trimmed email or 10 national digits.
  const [authValue, setAuthValue] = useState('');
  const [code, setCode] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [attendeeFirstName, setAttendeeFirstName] = useState('');
  const [attendeeMiddleName, setAttendeeMiddleName] = useState('');
  const [attendeeLastName, setAttendeeLastName] = useState('');
  const [attendeeOrganization, setAttendeeOrganization] = useState('');
  const [attendeeTitle, setAttendeeTitle] = useState('');
  const [attendeeOrgType, setAttendeeOrgType] = useState<OrganizationType>('organization');
  const [attendeeSecondaryEmail, setAttendeeSecondaryEmail] = useState('');
  const [attendeePhone, setAttendeePhone] = useState('');
  const [primaryEmail, setPrimaryEmail] = useState('');
  const [phoneRegion, setPhoneRegion] = useState('1-US');
  const [phoneCode, setPhoneCode] = useState('');
  const [phoneVerified, setPhoneVerified] = useState(false);
  const [normalizedPhone, setNormalizedPhone] = useState('');
  const [phoneSending, setPhoneSending] = useState(false);
  const [phoneCodeSent, setPhoneCodeSent] = useState(false);
  const [verifyingPhone, setVerifyingPhone] = useState(false);
  // Snapshot of the phone as loaded from the member profile. Held in state (not a ref)
  // because `phoneChanged` is derived during render and must react when the snapshot is set.
  const [initialPhone, setInitialPhone] = useState<{digits: string; region: string} | null>(null);
  const initialProfileRef = useRef<{first_name: string; middle_name: string; last_name: string; organization: string; title: string} | null>(null);

  const selectedRegistrationPath = registrationPathForEvent(selectedEventSlug || eventSlugParam);
  const completeProfilePath = buildCompleteProfilePath(selectedRegistrationPath);
  const profileCompletionPathForQueryEvent = buildCompleteProfilePath(registrationPathForEvent(eventSlugParam));

  const resetEventForm = useCallback(() => {
    setOptions(null);
    setRegistration(null);
    setSelectedTicketId(null);
    setAnswers({});
    setAttendeeFirstName('');
    setAttendeeMiddleName('');
    setAttendeeLastName('');
    setAttendeeOrganization('');
    setAttendeeTitle('');
    setAttendeeOrgType('organization');
    setAttendeeSecondaryEmail('');
    setAttendeePhone('');
    setPrimaryEmail('');
    setPhoneRegion('1-US');
    setPhoneCode('');
    setPhoneVerified(false);
    setNormalizedPhone('');
    setPhoneCodeSent(false);
    setInitialPhone(null);
    initialProfileRef.current = null;
  }, []);

  // Pre-fill attendee fields from member profile.
  const prefillFromProfile = useCallback((data: EventRegistrationOptions) => {
    if (data.member_profile) {
      const p = data.member_profile;
      setAttendeeFirstName(p.first_name);
      setAttendeeMiddleName(p.middle_name);
      setAttendeeLastName(p.last_name);
      const org = p.organization || '';
      const normalized = org.trim().toLowerCase();
      const isIndividual = ['individual', 'personal'].includes(normalized);
      setAttendeeOrgType(isIndividual ? 'individual' : 'organization');
      setAttendeeOrganization(isIndividual ? '' : org);
      setAttendeeTitle(p.title || '');
      initialProfileRef.current = {
        first_name: p.first_name,
        middle_name: p.middle_name,
        last_name: p.last_name,
        organization: isIndividual ? 'Individual' : org,
        title: p.title || '',
      };
    }
  }, []);

  const syncEventRegistration = useCallback((eventSlug: string, nextRegistration: Registration | null) => {
    setEvents((current) =>
      current.map((event) =>
        event.slug === eventSlug
          ? {
              ...event,
              registration: nextRegistration,
            }
          : event,
      ),
    );
  }, []);

  const loadOptionsAndRoute = useCallback(async (eventSlug: string, fallbackToEventList = false) => {
    try {
      resetEventForm();
      setSelectedEventSlug(eventSlug);
      const data = await fetchRegistrationOptions(eventSlug);
      setOptions(data);
      syncEventRegistration(data.slug, data.registration);

      if (data.registration) {
        setRegistration(data.registration);
        setStep('done');
        return;
      }

      if (data.allow_secondary_email && data.member_emails?.length >= 2) {
        setAttendeeSecondaryEmail(data.member_emails[1]);
      }
      setPrimaryEmail(data.member_emails?.[0] || '');

      if (data.collect_phone && data.member_phone) {
        const phone = data.member_phone.phone_number || '';
        // US-only: strip a leading +1 to recover the national digits.
        const normalizedDigits = phone.startsWith('+1') ? phone.slice(2) : phone;
        setAttendeePhone(normalizedDigits || phone);
        setPhoneRegion('1-US');
        setPhoneVerified(Boolean(data.member_phone.verified));
        setPhoneCodeSent(Boolean(data.member_phone.verified));
        setInitialPhone({digits: normalizedDigits || phone, region: '1-US'});
      }
      if (data.member_profile && !hasRequiredNameFields(data.member_profile)) {
        navigate(buildCompleteProfilePath(registrationPathForEvent(data.slug)), {replace: true});
        return;
      }
      prefillFromProfile(data);
      setStep('form');
    } catch (err: unknown) {
      const axiosErr = err as {response?: {status?: number}};
      if (axiosErr.response?.status === 401) {
        setStep('email');
        return;
      }
      const message = getRegistrationErrorMessage(err);
      setError(
        message.toLowerCase().includes('accepting registrations')
          ? 'This event is not currently accepting registrations.'
          : message,
      );
      setStep(fallbackToEventList ? 'select' : 'loading');
    }
  }, [navigate, prefillFromProfile, resetEventForm, syncEventRegistration]);

  const loadPublicOptionsForEmailStep = useCallback(async (eventSlug: string) => {
    try {
      resetEventForm();
      setSelectedEventSlug(eventSlug);
      const data = await fetchRegistrationOptions(eventSlug);
      setOptions(data);
      syncEventRegistration(data.slug, data.registration);
      setStep('email');
    } catch (err: unknown) {
      setError(getRegistrationErrorMessage(err));
      setStep('email');
    }
  }, [resetEventForm, syncEventRegistration]);

  useEffect(() => {
    if (isAuthenticated && requiresProfileCompletion) {
      navigate(profileCompletionPathForQueryEvent, {replace: true});
      return;
    }

    let cancelled = false;
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

        const nextSlug = eventSlugParam || (eventList.length === 1 ? eventList[0].slug : '');
        if (!nextSlug) {
          setSelectedEventSlug('');
          setOptions(null);
          setRegistration(null);
          setStep('select');
          return;
        }

        if (!eventList.some((event) => event.slug === nextSlug)) {
          setSelectedEventSlug('');
          setOptions(null);
          setRegistration(null);
          setError('This event is not currently accepting registrations.');
          setStep(eventList.length > 1 ? 'select' : 'loading');
          return;
        }

        if (isAuthenticated) {
          await loadOptionsAndRoute(nextSlug, eventList.length > 1);
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
    };
  }, [
    eventSlugParam,
    isAuthenticated,
    loadOptionsAndRoute,
    loadPublicOptionsForEmailStep,
    navigate,
    profileCompletionPathForQueryEvent,
    requiresProfileCompletion,
  ]);

  const handleSelectEvent = (eventSlug: string) => {
    setError(null);
    navigate(registrationPathForEvent(eventSlug));
  };

  const handleShowEventList = () => {
    setError(null);
    setOptions(null);
    setRegistration(null);
    setSelectedEventSlug('');
    setStep(events.length > 0 ? 'select' : 'loading');
    navigate('/event-registration');
  };

  // Entry accepts an email OR a US phone number; route to the matching passwordless flow.
  const handleEmailSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const parsed = identifyLoginInput(email.trim());
    if (parsed.type === 'invalid') {
      setError('Please enter a valid email address or 10-digit US phone number.');
      return;
    }
    setAuthLoading(true);
    setError(null);
    try {
      if (parsed.type === 'email') {
        await requestEmailAuthCode(parsed.value, 'event_registration');
        setIdentifierType('email');
        setAuthValue(parsed.value);
      } else {
        await requestPhoneAuthCode(parsed.nationalDigits, '1-US', 'event_registration');
        setIdentifierType('phone');
        setAuthValue(parsed.nationalDigits);
      }
      setStep('code');
    } catch (err: unknown) {
      setError(getRegistrationErrorMessage(err));
    } finally {
      setAuthLoading(false);
    }
  };

  const handleCodeSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setAuthLoading(true);
    setError(null);
    try {
      const result =
        identifierType === 'phone'
          ? await verifyPhoneAuthCode(authValue, code.trim(), '1-US')
          : await verifyEmailAuthCode(authValue, code.trim());
      if (result.next_step === 'complete_profile' || result.requires_profile_completion) {
        navigate(completeProfilePath, {replace: true});
        return;
      }
      setStep('loading');
      if (selectedEventSlug) {
        await loadOptionsAndRoute(selectedEventSlug, events.length > 1);
      }
    } catch (err: unknown) {
      setError(getRegistrationErrorMessage(err));
    } finally {
      setAuthLoading(false);
    }
  };

  const handleRegistrationSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!options || !selectedTicketId || !attendeeFirstName.trim() || !attendeeLastName.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      // Sync profile if fields changed.
      const orgValue = attendeeOrgType === 'individual' ? 'Individual' : attendeeOrganization.trim();
      const titleValue = attendeeOrgType === 'organization' ? attendeeTitle.trim() : '';
      const prev = initialProfileRef.current;
      const profileChanged = !prev
        || prev.first_name !== attendeeFirstName.trim()
        || prev.middle_name !== attendeeMiddleName.trim()
        || prev.last_name !== attendeeLastName.trim()
        || prev.organization !== orgValue
        || prev.title !== titleValue;

      if (profileChanged) {
        await updateProfileFields({
          first_name: attendeeFirstName.trim(),
          middle_name: attendeeMiddleName.trim(),
          last_name: attendeeLastName.trim(),
          organization: orgValue,
          title: titleValue,
        });
      }

      const result = await createRegistration({
        event_slug: options.slug,
        ticket_id: selectedTicketId,
        attendee_first_name: attendeeFirstName.trim(),
        attendee_last_name: attendeeLastName.trim(),
        attendee_organization: orgValue,
        answers: Object.entries(answers).filter(([, value]) => value.trim()).map(([questionId, answer]) => ({question_id: questionId, answer})),
        attendee_secondary_email: options.allow_secondary_email ? attendeeSecondaryEmail.trim() || undefined : undefined,
        attendee_phone: options.collect_phone ? attendeePhone.trim() || undefined : undefined,
        attendee_phone_region: options.collect_phone && attendeePhone.trim() ? phoneRegion : undefined,
      });
      setRegistration(result);
      syncEventRegistration(options.slug, result);
      setStep('done');
    } catch (err: unknown) {
      const axiosErr = err as {response?: {status?: number; data?: {registration?: Registration}}};
      if (axiosErr.response?.status === 409 && axiosErr.response.data?.registration) {
        setRegistration(axiosErr.response.data.registration);
        syncEventRegistration(options.slug, axiosErr.response.data.registration);
        setStep('done');
      } else {
        setError(getRegistrationErrorMessage(err));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleSendPhoneCode = async () => {
    if (!attendeePhone.trim() || validatePhoneDigits(attendeePhone.trim())) return;
    setPhoneSending(true);
    setError(null);
    try {
      const result = await sendPhoneCode(attendeePhone.trim(), phoneRegion);
      setNormalizedPhone(result.phone);
      setPhoneCodeSent(true);
    } catch (err: unknown) {
      setError(getRegistrationErrorMessage(err));
    } finally {
      setPhoneSending(false);
    }
  };

  const handleVerifyPhoneCode = async () => {
    if (!normalizedPhone || !phoneCode.trim()) return;
    setVerifyingPhone(true);
    setError(null);
    try {
      const result = await verifyPhoneCode(normalizedPhone, phoneCode.trim());
      setNormalizedPhone(result.phone);
      setPhoneVerified(true);
      setError(null);
    } catch (err: unknown) {
      setError(getRegistrationErrorMessage(err));
    } finally {
      setVerifyingPhone(false);
    }
  };

  const handlePhoneChange = (value: string) => {
    const capped = value.slice(0, maxPhoneDigits());
    if (capped !== attendeePhone) {
      setPhoneVerified(false);
      setPhoneCodeSent(false);
      setPhoneCode('');
      setNormalizedPhone('');
    }
    setAttendeePhone(capped);
  };

  const phoneChanged = initialPhone === null
    || attendeePhone !== initialPhone.digits
    || phoneRegion !== initialPhone.region;

  const phoneError = useMemo(
    () => {
      if (!attendeePhone.trim()) return null;
      if (!phoneChanged) return null;
      return validatePhoneDigits(attendeePhone.trim());
    },
    [attendeePhone, phoneChanged],
  );

  return {
    answers,
    attendeeFirstName,
    attendeeMiddleName,
    attendeeLastName,
    attendeeOrganization,
    attendeeTitle,
    attendeeOrgType,
    attendeePhone,
    attendeeSecondaryEmail,
    primaryEmail,
    phoneError,
    phoneRegion,
    phoneCode,
    phoneCodeSent,
    phoneSending,
    phoneVerified,
    verifyingPhone,
    authLoading,
    code,
    email,
    error,
    events,
    options,
    registration,
    selectedEventSlug,
    selectedTicketId,
    step,
    submitting,
    setAnswers,
    setAttendeeFirstName,
    setAttendeeMiddleName,
    setAttendeeLastName,
    setAttendeeOrganization,
    setAttendeeTitle,
    setAttendeeOrgType,
    handlePhoneChange,
    setAttendeeSecondaryEmail,
    setPhoneCode,
    setCode,
    setEmail,
    setError,
    setSelectedTicketId,
    setStep,
    handleCodeSubmit,
    handleEmailSubmit,
    handleRegistrationSubmit,
    handleSelectEvent,
    handleShowEventList,
    handleSendPhoneCode,
    handleVerifyPhoneCode,
  };
};
