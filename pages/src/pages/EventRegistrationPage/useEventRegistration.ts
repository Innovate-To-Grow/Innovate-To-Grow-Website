import {useCallback, useEffect, useState, type FormEvent} from 'react';
import {useAuth} from '../../components/Auth';
import {updateProfileFields} from '../../services/auth';
import {createRegistration, fetchRegistrationOptions, type EventRegistrationOptions, type Registration} from '../../features/events/api';
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

  const loadOptions = useCallback(async () => {
    try {
      const data = await fetchRegistrationOptions();
      setOptions(data);
      if (data.registration) {
        setRegistration(data.registration);
        setStep('done');
      } else {
        setStep(isAuthenticated ? 'form' : 'email');
      }
    } catch (err: unknown) {
      const message = getRegistrationErrorMessage(err);
      const axiosErr = err as {response?: {status?: number}};
      if (axiosErr.response?.status === 401) return setStep('email');
      setError(message.toLowerCase().includes('no live event') ? 'No event is currently accepting registrations.' : message);
      setStep('loading');
    }
  }, [isAuthenticated]);

  useEffect(() => {
    void loadOptions();
  }, [loadOptions]);

  useEffect(() => {
    if (!isAuthenticated || (step !== 'email' && step !== 'code')) return;
    if (requiresProfileCompletion) {
      setStep('profile');
    } else {
      setStep('loading');
      void loadOptions();
    }
  }, [isAuthenticated, loadOptions, requiresProfileCompletion, step]);

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
      await verifyEmailAuthCode(email.trim(), code.trim());
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
      await loadOptions();
    } catch (err: unknown) {
      setError(getRegistrationErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleRegistrationSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!options || !selectedTicketId) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await createRegistration({
        event_slug: options.slug,
        ticket_id: selectedTicketId,
        answers: Object.entries(answers).filter(([, value]) => value.trim()).map(([questionId, answer]) => ({question_id: questionId, answer})),
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

  return {
    answers,
    authFlow,
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
  };
};
