import {useCallback, useState} from 'react';
import {useNavigate} from 'react-router';
import {buildCompleteProfilePath} from '@/features/auth/api/redirects';
import type {EventRegistrationOptions, Registration} from '@/features/events/api';
import {useAttendeeProfile} from './registration/useAttendeeProfile';
import {usePhoneVerification, type PhoneVerification} from './registration/usePhoneVerification';
import {registrationPathForEvent} from './registration/useEventOptionsLoader';
import {useRegistrationEvents} from './registration/useRegistrationEvents';
import {useRegistrationSignIn} from './registration/useRegistrationSignIn';
import {useRegistrationSubmit} from './registration/useRegistrationSubmit';
import {
  useSecondaryEmailVerification,
  type SecondaryEmailVerification,
} from './registration/useSecondaryEmailVerification';

export type {OrganizationType} from './registration/useAttendeeProfile';

type Options = EventRegistrationOptions | null;

/** The attendee profile under the names the page uses. */
const attendeeProfileView = (profile: ReturnType<typeof useAttendeeProfile>) => ({
  attendeeFirstName: profile.firstName,
  attendeeMiddleName: profile.middleName,
  attendeeLastName: profile.lastName,
  attendeeOrganization: profile.organization,
  attendeeTitle: profile.title,
  attendeeOrgType: profile.orgType,
  setAttendeeFirstName: profile.setFirstName,
  setAttendeeMiddleName: profile.setMiddleName,
  setAttendeeLastName: profile.setLastName,
  setAttendeeOrganization: profile.setOrganization,
  setAttendeeTitle: profile.setTitle,
  setAttendeeOrgType: profile.setOrgType,
});

/** The phone and its verification under the names the page uses. */
const phoneView = (phone: PhoneVerification, options: Options) => ({
  attendeePhone: phone.phone,
  phoneError: phone.phoneError,
  phoneRegion: phone.region,
  phoneCode: phone.code,
  phoneCodeSent: phone.codeSent,
  phoneSending: phone.sending,
  phoneVerified: phone.verified,
  verifyingPhone: phone.verifying,
  setPhoneCode: phone.setCode,
  handlePhoneChange: phone.changePhone,
  handleSendPhoneCode: () => phone.send(options),
  handleVerifyPhoneCode: () => phone.verify(options),
});

/** The secondary email and its verification under the names the page uses. */
const secondaryEmailView = (secondaryEmail: SecondaryEmailVerification, options: Options, primaryEmail: string) => ({
  attendeeSecondaryEmail: secondaryEmail.email,
  secondaryEmailCode: secondaryEmail.code,
  secondaryEmailCodeSent: secondaryEmail.codeSent,
  secondaryEmailSending: secondaryEmail.sending,
  secondaryEmailVerified: secondaryEmail.verified,
  verifyingSecondaryEmail: secondaryEmail.verifying,
  setSecondaryEmailCode: secondaryEmail.setCode,
  handleSendSecondaryEmailCode: () => secondaryEmail.send(options, primaryEmail),
  handleVerifySecondaryEmailCode: () => secondaryEmail.verify(options),
  handleSecondaryEmailChange: secondaryEmail.changeEmail,
});

/**
 * The event-registration flow: pick an event, sign in (email/phone code), fill and submit the form.
 * Composes the hooks in `registration/`: which event and step (`useRegistrationEvents`), sign-in, the
 * attendee profile, the two verifiable contacts, and submission. Returns the flat view the page renders.
 */
export const useEventRegistration = () => {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [primaryEmail, setPrimaryEmail] = useState('');
  const profile = useAttendeeProfile();
  const phone = usePhoneVerification(setError);
  const secondaryEmail = useSecondaryEmailVerification(setError);
  const {reset: resetProfile, prefill: prefillProfile} = profile;
  const {reset: resetPhone, prefill: prefillPhone, invalidate: invalidatePhone} = phone;
  const {reset: resetEmail, prefill: prefillEmail, invalidate: invalidateEmail} = secondaryEmail;

  const resetForm = useCallback(() => {
    setSelectedTicketId(null);
    setAnswers({});
    setPrimaryEmail('');
    resetProfile();
    resetPhone();
    resetEmail();
  }, [resetEmail, resetPhone, resetProfile]);

  const invalidateContacts = useCallback(() => {
    invalidatePhone();
    invalidateEmail();
  }, [invalidateEmail, invalidatePhone]);

  const prefillContacts = useCallback(
    (data: EventRegistrationOptions) => {
      if (data.allow_secondary_email) prefillEmail(data);
      setPrimaryEmail(data.member_primary_email ?? data.member_emails?.[0] ?? '');
      if (data.collect_phone && data.member_phone) prefillPhone(data.member_phone);
    },
    [prefillEmail, prefillPhone],
  );

  const flow = useRegistrationEvents({setError, resetForm, invalidateContacts, prefillContacts, prefillProfile});
  const {options, setStep} = flow;

  const signIn = useRegistrationSignIn({
    eventSlug: flow.currentEventSlug || undefined,
    setStep,
    setError,
    onProfileIncomplete: () =>
      navigate(buildCompleteProfilePath(registrationPathForEvent(flow.currentEventSlug)), {replace: true}),
    onSignedIn: async () => {
      if (flow.selectedEventSlug) {
        await flow.loadOptionsAndRoute(flow.selectedEventSlug, flow.events.length >= 1);
      }
    },
  });

  const submit = useRegistrationSubmit({
    options,
    selectedTicketId,
    answers,
    primaryEmail,
    profile,
    phone,
    secondaryEmail,
    setError,
    onRegistered: (eventSlug: string, registration: Registration) => {
      flow.setRegistration(registration);
      flow.syncEventRegistration(eventSlug, registration);
      setStep('done');
    },
  });

  return {
    ...attendeeProfileView(profile),
    ...phoneView(phone, options),
    ...secondaryEmailView(secondaryEmail, options, primaryEmail),
    answers,
    primaryEmail,
    authLoading: signIn.authLoading,
    code: signIn.code,
    email: signIn.email,
    error,
    events: flow.events,
    options,
    registration: flow.registration,
    selectedEventSlug: flow.selectedEventSlug,
    selectedTicketId,
    step: flow.step,
    submitting: submit.submitting,
    setAnswers,
    setCode: signIn.setCode,
    setEmail: signIn.setEmail,
    setError,
    setSelectedTicketId,
    setStep,
    handleCodeSubmit: signIn.handleCodeSubmit,
    handleEmailSubmit: signIn.handleEmailSubmit,
    handleRegistrationSubmit: submit.handleRegistrationSubmit,
    handleSelectEvent: flow.handleSelectEvent,
    handleShowEventList: flow.handleShowEventList,
  };
};
