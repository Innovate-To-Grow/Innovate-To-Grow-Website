import {getSecondaryEmailError} from '../helpers';
import type {RegistrationFormErrors, RegistrationFormStepProps} from './types';

type ContactErrors = Pick<
  RegistrationFormErrors,
  | 'missingPhone'
  | 'phoneNotVerified'
  | 'phoneHasError'
  | 'missingSecondaryEmail'
  | 'secondaryEmailNotVerified'
  | 'secondaryEmailError'
>;

function getPhoneErrors(form: RegistrationFormStepProps) {
  const {options} = form;
  const hasPhone = Boolean(form.attendeePhone.trim());
  return {
    missingPhone: options.collect_phone && options.require_phone && !hasPhone,
    phoneNotVerified: options.collect_phone && options.verify_phone && hasPhone && !form.phoneVerified,
    phoneHasError: options.collect_phone && Boolean(form.phoneError),
  };
}

function getSecondaryEmailErrors(form: RegistrationFormStepProps) {
  const {options} = form;
  if (!options.allow_secondary_email) {
    return {missingSecondaryEmail: false, secondaryEmailNotVerified: false, secondaryEmailError: null};
  }
  const hasSecondaryEmail = Boolean(form.attendeeSecondaryEmail.trim());
  return {
    missingSecondaryEmail: options.require_secondary_email && !hasSecondaryEmail,
    secondaryEmailNotVerified: options.verify_secondary_email && hasSecondaryEmail && !form.secondaryEmailVerified,
    secondaryEmailError: getSecondaryEmailError(form.attendeeSecondaryEmail, form.primaryEmail),
  };
}

function getContactErrors(form: RegistrationFormStepProps): ContactErrors {
  return {...getPhoneErrors(form), ...getSecondaryEmailErrors(form)};
}

export function getRegistrationFormErrors(form: RegistrationFormStepProps): RegistrationFormErrors {
  const {options} = form;
  return {
    missingFirstName: !form.attendeeFirstName.trim(),
    missingLastName: !form.attendeeLastName.trim(),
    missingOrganization: form.attendeeOrgType === 'organization' && !form.attendeeOrganization.trim(),
    missingTicket: !form.selectedTicketId,
    ...getContactErrors(form),
    missingAnswerIds: new Set(
      options.questions.filter((q) => q.is_required && !form.answers[q.id]?.trim()).map((q) => q.id),
    ),
  };
}

export function hasRegistrationFormErrors(errors: RegistrationFormErrors): boolean {
  // Every other field is a boolean "this is wrong" flag (or an error message).
  const {missingAnswerIds, ...flags} = errors;
  return missingAnswerIds.size > 0 || Object.values(flags).some(Boolean);
}
