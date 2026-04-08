import {useCallback, useEffect, useRef, useState, type FormEvent} from 'react';
import {useAuth} from '../../components/Auth';
import {updateProfileFields} from '../../services/auth';
import {createRegistration, fetchRegistrationOptions, sendPhoneCode, verifyPhoneCode, type EventRegistrationOptions, type Registration} from '../../features/events/api';
import {getRegistrationErrorMessage, type EventRegistrationStep} from './steps/helpers';

export type OrganizationType = 'personal' | 'organization';

export const useEventRegistration = () => {
  const {isAuthenticated, requestEmailAuthCode, verifyEmailAuthCode, clearProfileCompletionRequirement} = useAuth();
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
  const [organizationType, setOrganizationType] = useState<OrganizationType>('personal');
  const [saving, setSaving] = useState(false);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [attendeeFirstName, setAttendeeFirstName] = useState('');
  const [attendeeLastName, setAttendeeLastName] = useState('');
  const [attendeeOrganization, setAttendeeOrganization] = useState('');
  const [attendeeOrgType, setAttendeeOrgType] = useState<OrganizationType>('personal');
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
  const [profileCompleted, setProfileCompleted] = useState(false);
  const [accountInfoLocked, setAccountInfoLocked] = useState(false);
  const [accountPhoneLocked, setAccountPhoneLocked] = useState(false);
  const [accountSecondaryEmailLocked, setAccountSecondaryEmailLocked] = useState(false);
  const optionsLoaded = useRef(false);

  // Pre-fill attendee fields from member profile
  const prefillFromProfile = useCallback((data: EventRegistrationOptions) => {
    if (data.member_profile) {
      const p = data.member_profile;
      setAttendeeFirstName((prev) => prev || p.first_name);
      setAttendeeLastName((prev) => prev || p.last_name);
      const org = p.organization || '';
      const isPersonal = !org || org.toLowerCase() === 'personal';
      setAttendeeOrgType((prev) => prev !== 'organization' ? (isPersonal ? 'personal' : 'organization') : prev);
      setAttendeeOrganization((prev) => prev || (isPersonal ? '' : org));
      setAccountInfoLocked(Boolean(p.first_name || p.last_name || org));
    } else {
      setAccountInfoLocked(false);
    }
  }, []);

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
        setAccountSecondaryEmailLocked(true);
      } else {
        setAccountSecondaryEmailLocked(false);
      }
      setPrimaryEmail(data.member_emails?.[0] || '');

      if (data.collect_phone && data.member_phone) {
        const phone = data.member_phone.phone_number || '';
        const region = data.member_phone.region || '1-US';
        const countryCode = region.split('-')[0];
        const normalizedDigits = phone.startsWith(`+${countryCode}`) ? phone.slice(countryCode.length + 1) : phone;
        setAttendeePhone((prev) => prev || normalizedDigits || phone);
        setPhoneRegion(region);
        setPhoneVerified(Boolean(data.member_phone.verified));
        setPhoneCodeSent(Boolean(data.member_phone.verified));
        setAccountPhoneLocked(Boolean(phone));
      } else {
        setAccountPhoneLocked(false);
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
      setError(message.toLowerCase().includes('no live event') ? 'No event is currently accepting registrations.' : message);
      setStep('loading');
    }
  }, [prefillFromProfile]);

  // On mount: load options to determine initial step
  useEffect(() => {
    if (isAuthenticated) {
      void loadOptionsAndRoute();
    } else {
      // Not authenticated — load options for event banner + email step
      fetchRegistrationOptions()
        .then((data) => {
          setOptions(data);
          optionsLoaded.current = true;
          setStep('email');
        })
        .catch((err: unknown) => {
          setError(getRegistrationErrorMessage(err));
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
    if (!lastName.trim()) return setError('Last name is required.');
    if (organizationType === 'organization' && !organization.trim()) return setError('Organization name is required.');
    setSaving(true);
    setError(null);
    try {
      const orgValue = organizationType === 'personal' ? 'Personal' : organization.trim();
      await updateProfileFields({
        first_name: firstName.trim(),
        middle_name: middleName.trim(),
        last_name: lastName.trim(),
        organization: orgValue,
      });
      clearProfileCompletionRequirement();
      // Pre-fill attendee fields from profile so name/org fields are hidden in form step
      setAttendeeFirstName(firstName.trim());
      setAttendeeLastName(lastName.trim());
      if (organizationType === 'organization' && organization.trim()) {
        setAttendeeOrgType('organization');
        setAttendeeOrganization(organization.trim());
      }
      setProfileCompleted(true);
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
      const orgValue = attendeeOrgType === 'personal' ? 'Personal' : attendeeOrganization.trim();
      const result = await createRegistration({
        event_slug: options.slug,
        ticket_id: selectedTicketId,
        attendee_first_name: attendeeFirstName.trim(),
        attendee_last_name: attendeeLastName.trim() || undefined,
        attendee_organization: orgValue,
        answers: Object.entries(answers).filter(([, value]) => value.trim()).map(([questionId, answer]) => ({question_id: questionId, answer})),
        attendee_secondary_email: options.allow_secondary_email ? attendeeSecondaryEmail.trim() || undefined : undefined,
        attendee_phone: options.collect_phone ? attendeePhone.trim() || undefined : undefined,
        attendee_phone_region: options.collect_phone && attendeePhone.trim() ? phoneRegion : undefined,
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
    if (value !== attendeePhone) {
      setPhoneVerified(false);
      setPhoneCodeSent(false);
      setPhoneCode('');
      setNormalizedPhone('');
    }
    setAttendeePhone(value);
  };

  const handlePhoneRegionChange = (value: string) => {
    if (value !== phoneRegion) {
      setPhoneVerified(false);
      setPhoneCodeSent(false);
      setPhoneCode('');
      setNormalizedPhone('');
    }
    setPhoneRegion(value);
  };

  return {
    answers,
    attendeeFirstName,
    attendeeLastName,
    attendeeOrganization,
    attendeeOrgType,
    attendeePhone,
    attendeeSecondaryEmail,
    primaryEmail,
    accountInfoLocked,
    accountPhoneLocked,
    accountSecondaryEmailLocked,
    phoneRegion,
    authFlow,
    phoneCode,
    phoneCodeSent,
    phoneSending,
    phoneVerified,
    profileCompleted,
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
    organizationType,
    registration,
    saving,
    selectedTicketId,
    step,
    submitting,
    setAnswers,
    setAttendeeFirstName,
    setAttendeeLastName,
    setAttendeeOrganization,
    setAttendeeOrgType,
    handlePhoneChange,
    setAttendeeSecondaryEmail,
    handlePhoneRegionChange,
    setPhoneCode,
    setCode,
    setEmail,
    setError,
    setFirstName,
    setLastName,
    setMiddleName,
    setOrganization,
    setOrganizationType,
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
