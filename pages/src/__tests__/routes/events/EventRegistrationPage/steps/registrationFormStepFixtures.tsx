import type {ComponentProps} from 'react';
import {fireEvent, render, screen} from '@testing-library/react';
import {vi} from 'vitest';

import type {EventRegistrationOptions} from '@/features/events/api';
import {RegistrationFormStep} from '@/routes/events/EventRegistrationPage/steps/form/RegistrationFormStep';

export type RegistrationFormStepProps = ComponentProps<typeof RegistrationFormStep>;

const baseOptions: EventRegistrationOptions = {
  id: 'event-1',
  name: 'Demo Day',
  slug: 'demo-day',
  date: '2026-05-01',
  location: 'Campus',
  description: 'Event description',
  allow_secondary_email: false,
  collect_phone: false,
  verify_phone: false,
  require_phone: false,
  verify_secondary_email: false,
  require_secondary_email: false,
  tickets: [{id: 'ticket-1', name: 'General Admission'}],
  questions: [],
  registration: null,
  member_emails: ['ada@example.com'],
  member_secondary_email: null,
  member_profile: {
    first_name: 'Ada',
    middle_name: '',
    last_name: 'Lovelace',
    organization: 'Individual',
    title: '',
  },
  member_phone: null,
  phone_regions: [{code: '1-US', label: 'United States'}],
};

export const renderForm = (
  optionOverrides: Partial<EventRegistrationOptions> = {},
  propOverrides: Partial<RegistrationFormStepProps> = {},
) => {
  const onSubmit = vi.fn();
  const props: RegistrationFormStepProps = {
    options: {...baseOptions, ...optionOverrides},
    selectedTicketId: 'ticket-1',
    answers: {},
    submitting: false,
    attendeeFirstName: 'Ada',
    attendeeMiddleName: '',
    attendeeLastName: 'Lovelace',
    attendeeOrgType: 'individual',
    attendeeOrganization: '',
    attendeeTitle: '',
    attendeeSecondaryEmail: '',
    attendeePhone: '',
    primaryEmail: 'ada@example.com',
    phoneError: null,
    onFirstNameChange: vi.fn(),
    onMiddleNameChange: vi.fn(),
    onLastNameChange: vi.fn(),
    onOrgTypeChange: vi.fn(),
    onOrganizationChange: vi.fn(),
    onTitleChange: vi.fn(),
    onTicketChange: vi.fn(),
    onAnswerChange: vi.fn(),
    onSecondaryEmailChange: vi.fn(),
    onPhoneChange: vi.fn(),
    secondaryEmailCode: '',
    secondaryEmailCodeSent: false,
    secondaryEmailSending: false,
    secondaryEmailVerified: false,
    verifyingSecondaryEmail: false,
    onSecondaryEmailCodeChange: vi.fn(),
    onSendSecondaryEmailCode: vi.fn(),
    onVerifySecondaryEmailCode: vi.fn(),
    phoneCode: '',
    phoneCodeSent: false,
    phoneSending: false,
    phoneVerified: false,
    verifyingPhone: false,
    onPhoneCodeChange: vi.fn(),
    onSendPhoneCode: vi.fn(),
    onVerifyPhoneCode: vi.fn(),
    ...propOverrides,
    onSubmit,
  };

  render(<RegistrationFormStep {...props} />);
  return {onSubmit};
};

export const submitForm = () => {
  fireEvent.submit(screen.getByRole('button', {name: 'Register'}).closest('form')!);
};
