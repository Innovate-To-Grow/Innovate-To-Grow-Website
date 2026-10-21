import type {FormEvent} from 'react';
import type {EventRegistrationOptions} from '@/features/events/api';
import type {OrganizationType} from '../../useEventRegistration';

export interface RegistrationFormStepProps {
  options: EventRegistrationOptions;
  selectedTicketId: string | null;
  answers: Record<string, string>;
  submitting: boolean;
  attendeeFirstName: string;
  attendeeMiddleName: string;
  attendeeLastName: string;
  attendeeOrgType: OrganizationType;
  attendeeOrganization: string;
  attendeeTitle: string;
  attendeeSecondaryEmail: string;
  attendeePhone: string;
  primaryEmail: string;
  phoneError: string | null;
  onFirstNameChange: (value: string) => void;
  onMiddleNameChange: (value: string) => void;
  onLastNameChange: (value: string) => void;
  onOrgTypeChange: (value: OrganizationType) => void;
  onOrganizationChange: (value: string) => void;
  onTitleChange: (value: string) => void;
  onTicketChange: (ticketId: string) => void;
  onAnswerChange: (questionId: string, answer: string) => void;
  onSecondaryEmailChange: (value: string) => void;
  onPhoneChange: (value: string) => void;
  secondaryEmailCode: string;
  secondaryEmailCodeSent: boolean;
  secondaryEmailSending: boolean;
  secondaryEmailVerified: boolean;
  verifyingSecondaryEmail: boolean;
  onSecondaryEmailCodeChange: (value: string) => void;
  onSendSecondaryEmailCode: () => void;
  onVerifySecondaryEmailCode: () => void;
  phoneCode: string;
  phoneCodeSent: boolean;
  phoneSending: boolean;
  phoneVerified: boolean;
  verifyingPhone: boolean;
  onPhoneCodeChange: (value: string) => void;
  onSendPhoneCode: () => void;
  onVerifyPhoneCode: () => void;
  onSubmit: (event: FormEvent) => void;
}

/** Which fields block submitting; shown only once the attendee has tried to submit. */
export interface RegistrationFormErrors {
  missingFirstName: boolean;
  missingLastName: boolean;
  missingOrganization: boolean;
  missingTicket: boolean;
  missingPhone: boolean;
  phoneNotVerified: boolean;
  phoneHasError: boolean;
  missingSecondaryEmail: boolean;
  secondaryEmailNotVerified: boolean;
  secondaryEmailError: string | null;
  missingAnswerIds: Set<string>;
}

export interface FormSectionProps {
  form: RegistrationFormStepProps;
  errors: RegistrationFormErrors;
  showError: boolean;
  /** ' event-reg-form-group--error' while errors show and `condition` holds. */
  errorClass: (condition: boolean) => string;
}
