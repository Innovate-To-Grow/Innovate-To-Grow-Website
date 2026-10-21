import {useState, type FormEvent} from 'react';
import {updateProfileFields} from '@/features/auth';
import {createRegistration, type EventRegistrationOptions, type Registration} from '@/features/events/api';
import {getRegistrationErrorMessage, normalizeRegistrationEmail} from '../steps/helpers';
import {buildRegistrationPayload, contactSubmissionError, type ContactState} from './registrationSubmission';
import type {useAttendeeProfile} from './useAttendeeProfile';
import type {PhoneVerification} from './usePhoneVerification';
import type {SecondaryEmailVerification} from './useSecondaryEmailVerification';

type RegistrationError = {response?: {status?: number; data?: {registration?: Registration; code?: string}}};

/** The registration a 409 reports when the attendee is already registered. */
const existingRegistration = (err: unknown) => {
  const response = (err as RegistrationError).response;
  return response?.status === 409 ? (response.data?.registration ?? null) : null;
};

const hasRequiredNames = (profile: ReturnType<typeof useAttendeeProfile>) =>
  Boolean(profile.firstName.trim() && profile.lastName.trim());

/** The contact fields the event collects, as they will be submitted. */
const contactStateFor = (
  options: EventRegistrationOptions,
  phone: PhoneVerification,
  secondaryEmail: SecondaryEmailVerification,
  primaryEmail: string,
): ContactState => ({
  phone: options.collect_phone ? phone.phone.trim() : '',
  phoneError: phone.phoneError,
  phoneVerified: phone.verified,
  secondaryEmail: options.allow_secondary_email ? normalizeRegistrationEmail(secondaryEmail.email) : '',
  secondaryEmailVerified: secondaryEmail.verified,
  primaryEmail,
});

interface UseRegistrationSubmitOptions {
  options: EventRegistrationOptions | null;
  selectedTicketId: string | null;
  answers: Record<string, string>;
  primaryEmail: string;
  profile: ReturnType<typeof useAttendeeProfile>;
  phone: PhoneVerification;
  secondaryEmail: SecondaryEmailVerification;
  setError: (message: string | null) => void;
  /** The registration exists (created now, or found already registered). */
  onRegistered: (eventSlug: string, registration: Registration) => void;
}

/** Submitting the form: contact checks, the member-profile sync, then the registration itself. */
export function useRegistrationSubmit({
  options,
  selectedTicketId,
  answers,
  primaryEmail,
  profile,
  phone,
  secondaryEmail,
  setError,
  onRegistered,
}: UseRegistrationSubmitOptions) {
  const [submitting, setSubmitting] = useState(false);

  const submitRegistration = async (eventOptions: EventRegistrationOptions, ticketId: string, contact: ContactState) => {
    // Sync the member profile first when the attendee edited it.
    const submitted = profile.submittedProfile();
    if (profile.profileChanged(submitted)) {
      await updateProfileFields(submitted);
    }
    return createRegistration(
      buildRegistrationPayload(eventOptions, {
        ticketId,
        firstName: submitted.first_name,
        lastName: submitted.last_name,
        organization: submitted.organization,
        answers,
        contact,
        phoneRegion: phone.region,
        phoneChallengeId: phone.challengeId,
        secondaryEmailChallengeId: secondaryEmail.challengeId,
        secondaryEmailVerificationToken: secondaryEmail.verificationToken,
      }),
    );
  };

  const handleFailure = (eventOptions: EventRegistrationOptions, err: unknown) => {
    const existing = existingRegistration(err);
    // Already registered (another tab, a double submit): show that registration.
    if (existing) {
      onRegistered(eventOptions.slug, existing);
      return;
    }
    // The server no longer accepts a verification it was sent: ask for a fresh code.
    const code = (err as RegistrationError).response?.data?.code;
    if (code === 'phone_verification_required') phone.clearChallenge();
    if (code === 'secondary_email_verification_required') secondaryEmail.clearChallenge();
    setError(getRegistrationErrorMessage(err));
  };

  const handleRegistrationSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!options || !selectedTicketId || !hasRequiredNames(profile)) return;
    const contact = contactStateFor(options, phone, secondaryEmail, primaryEmail);
    const contactError = contactSubmissionError(options, contact);
    if (contactError) {
      setError(contactError);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      onRegistered(options.slug, await submitRegistration(options, selectedTicketId, contact));
    } catch (err: unknown) {
      handleFailure(options, err);
    } finally {
      setSubmitting(false);
    }
  };

  return {submitting, handleRegistrationSubmit};
}

