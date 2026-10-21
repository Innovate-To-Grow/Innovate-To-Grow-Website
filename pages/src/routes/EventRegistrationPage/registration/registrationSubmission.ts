import type {EventRegistrationOptions, createRegistration} from '@/features/events/api';
import {getSecondaryEmailError} from '../steps/helpers';

type RegistrationPayload = Parameters<typeof createRegistration>[0];

export interface ContactState {
  /** Trimmed phone, or '' when the event does not collect one. */
  phone: string;
  phoneError: string | null;
  phoneVerified: boolean;
  /** Normalized secondary email, or '' when the event does not allow one. */
  secondaryEmail: string;
  secondaryEmailVerified: boolean;
  primaryEmail: string;
}

/** The first contact problem that blocks submitting, in the order the form lists them. */
type ContactCheck = [applies: boolean, message: string | null];

function phoneChecks(options: EventRegistrationOptions, contact: ContactState): ContactCheck[] {
  const hasPhone = Boolean(contact.phone);
  return [
    [options.collect_phone && options.require_phone && !hasPhone, 'Phone number is required.'],
    [hasPhone, contact.phoneError],
    [hasPhone && options.verify_phone && !contact.phoneVerified, 'Phone number must be verified.'],
  ];
}

function secondaryEmailChecks(options: EventRegistrationOptions, contact: ContactState): ContactCheck[] {
  const {secondaryEmail} = contact;
  const hasEmail = Boolean(secondaryEmail);
  return [
    [options.allow_secondary_email && options.require_secondary_email && !hasEmail, 'Secondary email is required.'],
    [hasEmail, hasEmail ? getSecondaryEmailError(secondaryEmail, contact.primaryEmail) : null],
    [hasEmail && options.verify_secondary_email && !contact.secondaryEmailVerified, 'Secondary email must be verified.'],
  ];
}

export function contactSubmissionError(options: EventRegistrationOptions, contact: ContactState): string | null {
  const checks = [...phoneChecks(options, contact), ...secondaryEmailChecks(options, contact)];
  for (const [applies, message] of checks) {
    if (applies && message) return message;
  }
  return null;
}

interface PayloadInput {
  ticketId: string;
  firstName: string;
  lastName: string;
  organization: string;
  answers: Record<string, string>;
  contact: ContactState;
  phoneRegion: string;
  phoneChallengeId: string;
  secondaryEmailChallengeId: string;
  secondaryEmailVerificationToken: string;
}

const proofWhen = (send: boolean, value: string) => (send && value ? value : undefined);

/** Verification proofs, sent only for a verified contact the event verifies. */
function verificationProofs(options: EventRegistrationOptions, input: PayloadInput) {
  const {contact} = input;
  const sendEmailProof = Boolean(contact.secondaryEmail) && options.verify_secondary_email && contact.secondaryEmailVerified;
  const sendPhoneProof = options.collect_phone && Boolean(contact.phone) && options.verify_phone && contact.phoneVerified;
  return {
    secondary_email_verification_challenge_id: proofWhen(sendEmailProof, input.secondaryEmailChallengeId),
    secondary_email_verification_token: proofWhen(sendEmailProof, input.secondaryEmailVerificationToken),
    phone_verification_challenge_id: proofWhen(sendPhoneProof, input.phoneChallengeId),
  };
}

/** The create-registration request. */
export function buildRegistrationPayload(options: EventRegistrationOptions, input: PayloadInput): RegistrationPayload {
  const {contact} = input;
  return {
    event_slug: options.slug,
    ticket_id: input.ticketId,
    attendee_first_name: input.firstName,
    attendee_last_name: input.lastName,
    attendee_organization: input.organization,
    answers: Object.entries(input.answers)
      .filter(([, value]) => value.trim())
      .map(([questionId, answer]) => ({question_id: questionId, answer})),
    attendee_secondary_email: contact.secondaryEmail || undefined,
    attendee_phone: options.collect_phone ? contact.phone || undefined : undefined,
    attendee_phone_region: options.collect_phone && contact.phone ? input.phoneRegion : undefined,
    ...verificationProofs(options, input),
  };
}
