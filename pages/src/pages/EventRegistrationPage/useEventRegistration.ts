import {useCallback, useEffect, useRef, useState, type FormEvent} from 'react';
import {useAuth} from '../../components/Auth';
import {updateProfileFields} from '../../services/auth';
import {createRegistration, fetchRegistrationOptions, sendPhoneCode, verifyPhoneCode, type EventRegistrationOptions, type Registration} from '../../features/events/api';
import {getRegistrationErrorMessage, type EventRegistrationStep} from './steps/helpers';

export const useEventRegistration = () => {
  const {isAuthenticated, requiresProfileCompletion, requestEmailAuthCode, verifyEmailAuthCode, clearProfileCompletionRequirement} = useAuth();
  const [step, setStep] = useState<EventRegistrationStep>('loading');
  const [options, setOptions] = useState<EventRegistrationOptions | null>(null);
  const [registration, setRegistration] = useState<Registration | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [authFlow, setAuthFlow] = useState<string | null>(null);
  const [firstName, setFirstName] = useState('');
  const [middleName, setMiddleName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organization, setOrganization] = useState('');
  const [saving, setSaving] = useState(false);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [attendeeFirstName, setAttendeeFirstName] = useState('');
  const [attendeeLastName, setAttendeeLastName] = useState('');
  const [attendeeSecondaryEmail, setAttendeeSecondaryEmail] = useState('');
  const [attendeePhone, setAttendeePhone] = useState('');
  const [phoneRegion, setPhoneRegion] = useState('1-US');
  const [phoneCode, setPhoneCode] = useState('');
  const [phoneVerified, setPhoneVerified] = useState(false);
  const [normalizedPhone, setNormalizedPhone] = useState('');
  const [phoneSending, setPhoneSending] = useState(false);
  const [phoneCodeSent, setPhoneCodeSent] = useState(false);
  const [verifyingPhone, setVerifyingPhone] = useState(false);
  const optionsLoaded = useRef(false);

  // Core function: fetch options and decide the next step
  const loadOptionsAndRoute = useCallback(async () => {
    try {
      const data = await fetchRegistrationOptions();
      setOptions(data);
      optionsLoaded.current = true;

      if (data.registration) {
        setRegistration(data.registration);
        setStep('done');
        return;
      }

      if (data.allow_secondary_email && data.member_emails?.length >= 2) {
        setAttendeeSecondaryEmail((prev) => prev || data.member_emails[1]);
      }
      setStep('form');
    } catch (err: unknown) {
      const axiosErr = err as {response?: {status?: number}};
      if (axiosErr.response?.status === 401) {
        setStep('email');
        return;
      }
      const message = getRegistrationErrorMessage(err);
      setError(message.toLowerCase().includes('no live event') ? 'No event is currently accepting registrations.' : message);
      setStep('loading');
    }
  }, []);

  // On mount: load options to determine initial step
  useEffect(() => {
    if (isAuthenticated) {
      void loadOptionsAndRoute();
    } else {
      // Not authenticated — try loading options anyway (to get event info), then show email step
      fetchRegistrationOptions()
        .then((data) => {
          setOptions(data);
          optionsLoaded.current = true;
          setStep('email');
        })
        .catch(() => {
          setStep('email');
        });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleEmailSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setAuthLoading(true);
    setError(null);
    try {
      const result = await requestEmailAuthCode(email.trim());
      setAuthFlow(result.flow);
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
      const result = await verifyEmailAuthCode(email.trim(), code.trim());
      // Auth succeeded — decide next step directly
      if (result.requires_profile_completion) {
        setStep('profile');
      } else {
        setStep('loading');
        await loadOptionsAndRoute();
      }
    } catch (err: unknown) {
      setError(getRegistrationErrorMessage(err));
    } finally {
      setAuthLoading(false);
    }
  };

  const handleProfileSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!firstName.trim()) return setError('First name is required.');
    setSaving(true);
    setError(null);
    try {
      await updateProfileFields({
        first_name: firstName.trim(),
        middle_name: middleName.trim(),
        last_name: lastName.trim(),
        organization: organization.trim(),
      });
      clearProfileCompletionRequirement();
      setStep('loading');
      await loadOptionsAndRoute();
    } catch (err: unknown) {
      setError(getRegistrationErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleRegistrationSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!options || !selectedTicketId || !attendeeFirstName.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await createRegistration({
        event_slug: options.slug,
        ticket_id: selectedTicketId,
        attendee_first_name: attendeeFirstName.trim(),
        attendee_last_name: attendeeLastName.trim() || undefined,
        answers: Object.entries(answers).filter(([, value]) => value.trim()).map(([questionId, answer]) => ({question_id: questionId, answer})),
        attendee_secondary_email: options.allow_secondary_email ? attendeeSecondaryEmail.trim() || undefined : undefined,
        attendee_phone: options.collect_phone ? attendeePhone.trim() || undefined : undefined,
        attendee_phone_region: options.collect_phone && attendeePhone.trim() ? phoneRegion : undefined,
        phone_verified: phoneVerified || undefined,
      });
      setRegistration(result);
      setStep('done');
    } catch (err: unknown) {
      const axiosErr = err as {response?: {status?: number; data?: {registration?: Registration}}};
      if (axiosErr.response?.status === 409 && axiosErr.response.data?.registration) {
        setRegistration(axiosErr.response.data.registration);
        setStep('done');
      } else {
        setError(getRegistrationErrorMessage(err));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleSendPhoneCode = async () => {
    if (!attendeePhone.trim()) return;
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
      await verifyPhoneCode(normalizedPhone, phoneCode.trim());
      setPhoneVerified(true);
      setError(null);
    } catch (err: unknown) {
      setError(getRegistrationErrorMessage(err));
    } finally {
      setVerifyingPhone(false);
    }
  };

  return {
    answers,
    attendeeFirstName,
    attendeeLastName,
    attendeePhone,
    attendeeSecondaryEmail,
    phoneRegion,
    authFlow,
    phoneCode,
    phoneCodeSent,
    phoneSending,
    phoneVerified,
    verifyingPhone,
    authLoading,
    code,
    email,
    error,
    firstName,
    lastName,
    middleName,
    options,
    organization,
    registration,
    saving,
    selectedTicketId,
    step,
    submitting,
    setAnswers,
    setAttendeeFirstName,
    setAttendeeLastName,
    setAttendeePhone,
    setAttendeeSecondaryEmail,
    setPhoneRegion,
    setPhoneCode,
    setCode,
    setEmail,
    setError,
    setFirstName,
    setLastName,
    setMiddleName,
    setOrganization,
    setSelectedTicketId,
    setStep,
    handleCodeSubmit,
    handleEmailSubmit,
    handleProfileSubmit,
    handleRegistrationSubmit,
    handleSendPhoneCode,
    handleVerifyPhoneCode,
  };
};
