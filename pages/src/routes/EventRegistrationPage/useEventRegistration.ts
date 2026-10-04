import {useCallback, useEffect, useRef, useState, type FormEvent} from 'react';
import {useNavigate, useSearchParams} from 'react-router';
import {useAuth} from '@/features/auth';
import {updateProfileFields} from '@/features/auth';
import {
  createRegistration,
  fetchRegistrationEvents,
  fetchRegistrationOptions,
  sendPhoneCode,
  verifyPhoneCode,
  sendSecondaryEmailCode,
  verifySecondaryEmailCode,
  type EventRegistrationOptions,
  type EventRegistrationSummary,
  type Registration,
} from '@/features/events/api';
import {maxPhoneDigits, validatePhoneDigits} from '@/lib/format';
import {hasRequiredNameFields} from '@/features/auth/api/profileCompletion';
import {buildCompleteProfilePath} from '@/features/auth/api/redirects';
import {identifyLoginInput} from '@/features/auth/components/sections/internal/identifyLoginInput';
import {getRegistrationErrorMessage, getSecondaryEmailError, normalizeRegistrationEmail, type EventRegistrationStep} from './steps/helpers';

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
  const [searchParams, setSearchParams] = useSearchParams();
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
  const [secondaryEmailCode, setSecondaryEmailCode] = useState('');
  const [secondaryEmailVerified, setSecondaryEmailVerified] = useState(false);
  const [secondaryEmailChallengeId, setSecondaryEmailChallengeId] = useState('');
  const [secondaryEmailVerificationToken, setSecondaryEmailVerificationToken] = useState('');
  const [secondaryEmailSending, setSecondaryEmailSending] = useState(false);
  const [secondaryEmailCodeSent, setSecondaryEmailCodeSent] = useState(false);
  const [verifyingSecondaryEmail, setVerifyingSecondaryEmail] = useState(false);
  const [attendeePhone, setAttendeePhone] = useState('');
  const [primaryEmail, setPrimaryEmail] = useState('');
  const [phoneRegion, setPhoneRegion] = useState('1-US');
  const [phoneCode, setPhoneCode] = useState('');
  const [phoneVerified, setPhoneVerified] = useState(false);
  const [normalizedPhone, setNormalizedPhone] = useState('');
  const [phoneChallengeId, setPhoneChallengeId] = useState('');
  const [phoneSending, setPhoneSending] = useState(false);
  const [phoneCodeSent, setPhoneCodeSent] = useState(false);
  const [verifyingPhone, setVerifyingPhone] = useState(false);
  // Snapshot of the phone as loaded from the member profile. Held in state (not a ref)
  // because `phoneChanged` is derived during render and must react when the snapshot is set.
  const [initialPhone, setInitialPhone] = useState<{digits: string; region: string} | null>(null);
  const initialProfileRef = useRef<{first_name: string; middle_name: string; last_name: string; organization: string; title: string} | null>(null);

  // A changed contact or event invalidates every in-flight verification response.
  const phoneRequestRef = useRef(0);
  const secondaryEmailRequestRef = useRef(0);

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
    phoneRequestRef.current += 1;
    secondaryEmailRequestRef.current += 1;
    setAttendeeSecondaryEmail('');
    setSecondaryEmailCode('');
    setSecondaryEmailVerified(false);
    setSecondaryEmailChallengeId('');
    setSecondaryEmailVerificationToken('');
    setSecondaryEmailSending(false);
    setSecondaryEmailCodeSent(false);
    setVerifyingSecondaryEmail(false);
    setPhoneSending(false);
    setVerifyingPhone(false);
    setAttendeePhone('');
    setPrimaryEmail('');
    setPhoneRegion('1-US');
    setPhoneCode('');
    setPhoneVerified(false);
    setNormalizedPhone('');
    setPhoneChallengeId('');
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

  // Guards against a superseded options fetch (rapid event switching) applying its state after
  // a newer request started; only the latest request may touch state past its await.
  const optionsRequestRef = useRef(0);

  const loadOptionsAndRoute = useCallback(async (eventSlug: string, fallbackToEventList = false) => {
    const requestId = ++optionsRequestRef.current;
    try {
      resetEventForm();
      setSelectedEventSlug(eventSlug);
      const data = await fetchRegistrationOptions(eventSlug);
      if (requestId !== optionsRequestRef.current) return;
      setOptions(data);
      syncEventRegistration(data.slug, data.registration);

      if (data.registration) {
        setRegistration(data.registration);
        setStep('done');
        return;
      }

      if (data.allow_secondary_email) {
        const secondaryEmail = data.member_secondary_email;
        // An older options response can prefill an address, but cannot establish verification.
        setAttendeeSecondaryEmail(secondaryEmail === undefined ? data.member_emails?.[1] || '' : secondaryEmail?.email_address || '');
        setSecondaryEmailVerified(Boolean(secondaryEmail?.verified));
      }
      setPrimaryEmail(data.member_primary_email ?? data.member_emails?.[0] ?? '');

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
      if (requestId !== optionsRequestRef.current) return;
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
    const requestId = ++optionsRequestRef.current;
    try {
      resetEventForm();
      setSelectedEventSlug(eventSlug);
      const data = await fetchRegistrationOptions(eventSlug);
      if (requestId !== optionsRequestRef.current) return;
      setOptions(data);
      syncEventRegistration(data.slug, data.registration);
      setStep('email');
    } catch (err: unknown) {
      if (requestId !== optionsRequestRef.current) return;
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
          // Recover onto the event list (even with a single open event) instead of a dead end.
          setStep('select');
          return;
        }

        if (isAuthenticated) {
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
      optionsRequestRef.current += 1;
      phoneRequestRef.current += 1;
      secondaryEmailRequestRef.current += 1;
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

  // Selection updates only the query string (never the pathname) so it works identically on
  // /event-registration and inside the chromeless /_embed/:embedSlug iframe; copying the current
  // params preserves the embed's hide-titles/hide-sections flags. Boot re-runs via eventSlugParam.
  const handleSelectEvent = (eventSlug: string) => {
    optionsRequestRef.current += 1;
    phoneRequestRef.current += 1;
    secondaryEmailRequestRef.current += 1;
    setError(null);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('event', eventSlug);
    setSearchParams(nextParams);
  };

  const handleShowEventList = () => {
    optionsRequestRef.current += 1;
    phoneRequestRef.current += 1;
    secondaryEmailRequestRef.current += 1;
    setError(null);
    setOptions(null);
    setRegistration(null);
    setSelectedEventSlug('');
    setStep(events.length > 0 ? 'select' : 'loading');
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('event');
    setSearchParams(nextParams);
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
        await requestEmailAuthCode(parsed.value, 'event_registration', selectedEventSlug || eventSlugParam || undefined);
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
        await loadOptionsAndRoute(selectedEventSlug, events.length >= 1);
      }
    } catch (err: unknown) {
      setError(getRegistrationErrorMessage(err));
    } finally {
      setAuthLoading(false);
    }
  };

  const phoneChanged = initialPhone === null
    || attendeePhone !== initialPhone.digits
    || phoneRegion !== initialPhone.region;
  const phoneError = attendeePhone.trim() && phoneChanged ? validatePhoneDigits(attendeePhone.trim()) : null;

  const handleRegistrationSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!options || !selectedTicketId || !attendeeFirstName.trim() || !attendeeLastName.trim()) return;
    const phone = options.collect_phone ? attendeePhone.trim() : '';
    const secondaryEmail = options.allow_secondary_email ? normalizeRegistrationEmail(attendeeSecondaryEmail) : '';
    const contactError = (options.collect_phone && options.require_phone && !phone ? 'Phone number is required.' : null)
      || (phone ? phoneError : null)
      || (phone && options.verify_phone && !phoneVerified ? 'Phone number must be verified.' : null)
      || (options.allow_secondary_email && options.require_secondary_email && !secondaryEmail ? 'Secondary email is required.' : null)
      || (secondaryEmail ? getSecondaryEmailError(secondaryEmail, primaryEmail) : null)
      || (secondaryEmail && options.verify_secondary_email && !secondaryEmailVerified ? 'Secondary email must be verified.' : null);
    if (contactError) {
      setError(contactError);
      return;
    }
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
        attendee_secondary_email: secondaryEmail || undefined,
        secondary_email_verification_challenge_id:
          secondaryEmail && options.verify_secondary_email && secondaryEmailVerified && secondaryEmailChallengeId
            ? secondaryEmailChallengeId : undefined,
        secondary_email_verification_token:
          secondaryEmail && options.verify_secondary_email && secondaryEmailVerified && secondaryEmailVerificationToken
            ? secondaryEmailVerificationToken : undefined,
        attendee_phone: options.collect_phone ? attendeePhone.trim() || undefined : undefined,
        attendee_phone_region: options.collect_phone && attendeePhone.trim() ? phoneRegion : undefined,
        phone_verification_challenge_id:
          options.collect_phone && phone && options.verify_phone && phoneVerified && phoneChallengeId
            ? phoneChallengeId
            : undefined,
      });
      setRegistration(result);
      syncEventRegistration(options.slug, result);
      setStep('done');
    } catch (err: unknown) {
      const axiosErr = err as {response?: {status?: number; data?: {registration?: Registration; code?: string}}};
      if (axiosErr.response?.status === 409 && axiosErr.response.data?.registration) {
        setRegistration(axiosErr.response.data.registration);
        syncEventRegistration(options.slug, axiosErr.response.data.registration);
        setStep('done');
      } else {
        const errorCode = axiosErr.response?.data?.code;
        if (errorCode === 'phone_verification_required') {
          phoneRequestRef.current += 1;
          setPhoneVerified(false);
          setPhoneCodeSent(false);
          setPhoneCode('');
          setNormalizedPhone('');
          setPhoneChallengeId('');
        }
        if (errorCode === 'secondary_email_verification_required') {
          secondaryEmailRequestRef.current += 1;
          setSecondaryEmailVerified(false);
          setSecondaryEmailCodeSent(false);
          setSecondaryEmailCode('');
          setSecondaryEmailChallengeId('');
          setSecondaryEmailVerificationToken('');
        }
        setError(getRegistrationErrorMessage(err));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleSendPhoneCode = async () => {
    const eventSlug = options?.slug;
    if (!eventSlug || !options.collect_phone || !options.verify_phone || !attendeePhone.trim() || validatePhoneDigits(attendeePhone.trim())) return;
    const requestId = ++phoneRequestRef.current;
    setPhoneSending(true);
    setVerifyingPhone(false);
    setPhoneVerified(false);
    setPhoneCodeSent(false);
    setPhoneCode('');
    setPhoneChallengeId('');
    setNormalizedPhone('');
    setError(null);
    try {
      const result = await sendPhoneCode(attendeePhone.trim(), phoneRegion, eventSlug);
      if (requestId !== phoneRequestRef.current) return;
      setNormalizedPhone(result.phone);
      setPhoneChallengeId(result.challenge_id);
      setPhoneCodeSent(true);
    } catch (err: unknown) {
      if (requestId === phoneRequestRef.current) setError(getRegistrationErrorMessage(err));
    } finally {
      if (requestId === phoneRequestRef.current) setPhoneSending(false);
    }
  };

  const handleVerifyPhoneCode = async () => {
    const eventSlug = options?.slug;
    if (!eventSlug || !options.collect_phone || !options.verify_phone || !normalizedPhone || !phoneChallengeId || phoneCode.length !== 6) return;
    const requestId = ++phoneRequestRef.current;
    setVerifyingPhone(true);
    setError(null);
    try {
      const result = await verifyPhoneCode(normalizedPhone, phoneCode.trim(), phoneChallengeId, eventSlug);
      if (requestId !== phoneRequestRef.current) return;
      setNormalizedPhone(result.phone);
      setPhoneChallengeId(result.challenge_id);
      setPhoneVerified(result.verified);
      setError(null);
    } catch (err: unknown) {
      if (requestId === phoneRequestRef.current) setError(getRegistrationErrorMessage(err));
    } finally {
      if (requestId === phoneRequestRef.current) setVerifyingPhone(false);
    }
  };

  const handlePhoneChange = (value: string) => {
    const capped = value.slice(0, maxPhoneDigits());
    if (capped !== attendeePhone) {
      phoneRequestRef.current += 1;
      setPhoneVerified(false);
      setPhoneCodeSent(false);
      setPhoneCode('');
      setNormalizedPhone('');
      setPhoneChallengeId('');
      setPhoneSending(false);
      setVerifyingPhone(false);
    }
    setAttendeePhone(capped);
  };

  const handleSecondaryEmailChange = (value: string) => {
    if (normalizeRegistrationEmail(value) !== normalizeRegistrationEmail(attendeeSecondaryEmail)) {
      secondaryEmailRequestRef.current += 1;
      setSecondaryEmailVerified(false);
      setSecondaryEmailCodeSent(false);
      setSecondaryEmailCode('');
      setSecondaryEmailChallengeId('');
      setSecondaryEmailVerificationToken('');
      setSecondaryEmailSending(false);
      setVerifyingSecondaryEmail(false);
    }
    setAttendeeSecondaryEmail(value);
  };

  const handleSendSecondaryEmailCode = async () => {
    const eventSlug = options?.slug;
    const email = normalizeRegistrationEmail(attendeeSecondaryEmail);
    if (!eventSlug || !options.allow_secondary_email || !options.verify_secondary_email || !email || getSecondaryEmailError(email, primaryEmail)) return;
    const requestId = ++secondaryEmailRequestRef.current;
    setSecondaryEmailSending(true);
    setVerifyingSecondaryEmail(false);
    setSecondaryEmailVerified(false);
    setSecondaryEmailCodeSent(false);
    setSecondaryEmailCode('');
    setSecondaryEmailChallengeId('');
    setSecondaryEmailVerificationToken('');
    setError(null);
    try {
      const result = await sendSecondaryEmailCode(email, eventSlug);
      if (requestId !== secondaryEmailRequestRef.current) return;
      setSecondaryEmailChallengeId(result.challenge_id);
      setSecondaryEmailCodeSent(true);
    } catch (err: unknown) {
      if (requestId === secondaryEmailRequestRef.current) setError(getRegistrationErrorMessage(err));
    } finally {
      if (requestId === secondaryEmailRequestRef.current) setSecondaryEmailSending(false);
    }
  };

  const handleVerifySecondaryEmailCode = async () => {
    const eventSlug = options?.slug;
    if (!eventSlug || !options.allow_secondary_email || !options.verify_secondary_email || !secondaryEmailChallengeId || secondaryEmailCode.length !== 6) return;
    const requestId = ++secondaryEmailRequestRef.current;
    setVerifyingSecondaryEmail(true);
    setError(null);
    try {
      const result = await verifySecondaryEmailCode(
        normalizeRegistrationEmail(attendeeSecondaryEmail), secondaryEmailCode, secondaryEmailChallengeId, eventSlug,
      );
      if (requestId !== secondaryEmailRequestRef.current) return;
      setSecondaryEmailChallengeId(result.challenge_id);
      setSecondaryEmailVerificationToken(result.verification_token);
      setSecondaryEmailVerified(result.verified);
      setError(null);
    } catch (err: unknown) {
      if (requestId === secondaryEmailRequestRef.current) setError(getRegistrationErrorMessage(err));
    } finally {
      if (requestId === secondaryEmailRequestRef.current) setVerifyingSecondaryEmail(false);
    }
  };


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
    secondaryEmailCode,
    secondaryEmailCodeSent,
    secondaryEmailSending,
    secondaryEmailVerified,
    verifyingSecondaryEmail,
    setSecondaryEmailCode,
    handleSendSecondaryEmailCode,
    handleVerifySecondaryEmailCode,
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
    handleSecondaryEmailChange,
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
