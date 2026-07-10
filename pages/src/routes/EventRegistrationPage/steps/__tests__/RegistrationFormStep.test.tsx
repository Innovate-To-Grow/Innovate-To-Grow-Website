import type {ComponentProps} from 'react';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import type {EventRegistrationOptions} from '@/features/events/api';
import {RegistrationFormStep} from '../RegistrationFormStep';

type RegistrationFormStepProps = ComponentProps<typeof RegistrationFormStep>;

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
  tickets: [{id: 'ticket-1', name: 'General Admission'}],
  questions: [],
  registration: null,
  member_emails: ['ada@example.com'],
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

const renderForm = (
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

const submitForm = () => {
  fireEvent.submit(screen.getByRole('button', {name: 'Register'}).closest('form')!);
};

describe('RegistrationFormStep', () => {
  afterEach(() => {
    cleanup();
  });

  it('blocks submission and shows a last-name error when last name is blank', () => {
    const {onSubmit} = renderForm({}, {attendeeLastName: ''});

    submitForm();

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Last name is required.')).toBeInTheDocument();
  });

  it('does not prompt for a phone number when phone collection is off', () => {
    const {onSubmit} = renderForm({collect_phone: false, verify_phone: false});

    expect(screen.queryByLabelText(/Phone Number/)).not.toBeInTheDocument();
    submitForm();
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('prompts for an optional phone number without requiring verification', () => {
    const {onSubmit} = renderForm({collect_phone: true, verify_phone: false});

    expect(screen.getByLabelText('Phone Number')).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Send Code'})).not.toBeInTheDocument();
    submitForm();
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('requires phone verification when both phone settings are on', () => {
    const {onSubmit} = renderForm({collect_phone: true, verify_phone: true});

    expect(screen.getByLabelText(/Phone Number/)).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Send Code'})).toBeInTheDocument();
    submitForm();
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Phone number must be verified.')).toBeInTheDocument();
  });

  it('does not block on stale verify_phone data when phone collection is off', () => {
    const {onSubmit} = renderForm({collect_phone: false, verify_phone: true});

    expect(screen.queryByLabelText(/Phone Number/)).not.toBeInTheDocument();
    submitForm();
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(screen.queryByText('Phone number must be verified.')).not.toBeInTheDocument();
  });
});
