import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';

import {RegistrationFormStep} from '@/routes/EventRegistrationPage/steps/RegistrationFormStep';
import type {EventRegistrationOptions} from '@/features/events/api';

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
    last_name: '',
    organization: 'Individual',
    title: '',
  },
  member_phone: null,
  phone_regions: [{code: '1-US', label: 'United States'}],
};

const renderForm = (overrides: Partial<Parameters<typeof RegistrationFormStep>[0]> = {}) => {
  const props = {
    options: baseOptions,
    selectedTicketId: 'ticket-1',
    answers: {},
    submitting: false,
    attendeeFirstName: 'Ada',
    attendeeMiddleName: '',
    attendeeLastName: 'Lovelace',
    attendeeOrgType: 'individual' as const,
    attendeeOrganization: '',
    attendeeTitle: '',
    attendeeSecondaryEmail: '',
    attendeePhone: '',
    primaryEmail: 'ada@example.com',
    phoneError: null,
    phoneRegion: '1-US',
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
    onPhoneRegionChange: vi.fn(),
    phoneCode: '',
    phoneCodeSent: false,
    phoneSending: false,
    phoneVerified: false,
    verifyingPhone: false,
    onPhoneCodeChange: vi.fn(),
    onSendPhoneCode: vi.fn(),
    onVerifyPhoneCode: vi.fn(),
    onSubmit: vi.fn(),
    ...overrides,
  };

  render(<RegistrationFormStep {...props} />);
  return props;
};

describe('RegistrationFormStep', () => {
  it('blocks submission and shows a last-name error when last name is blank', () => {
    const onSubmit = vi.fn();

    renderForm({attendeeLastName: '', onSubmit});

    fireEvent.submit(screen.getByRole('button', {name: 'Register'}).closest('form')!);

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Last name is required.')).toBeInTheDocument();
  });

  it('submits a valid registration and propagates field changes', () => {
    const options: EventRegistrationOptions = {
      ...baseOptions,
      allow_secondary_email: true,
      collect_phone: true,
      verify_phone: true,
      tickets: [
        {id: 'ticket-1', name: 'General Admission'},
        {id: 'ticket-2', name: 'VIP'},
      ],
      questions: [
        {id: 'q2', text: 'Dietary notes', is_required: false, order: 2},
        {id: 'q1', text: 'Why attend?', is_required: true, order: 1},
      ],
      phone_regions: [
        {code: '1-US', label: 'United States'},
        {code: '44-GB', label: 'United Kingdom'},
      ],
    };
    const onSubmit = vi.fn((event) => event.preventDefault());
    const props = renderForm({
      options,
      selectedTicketId: 'ticket-1',
      answers: {q1: 'To learn'},
      attendeeOrgType: 'organization',
      attendeeOrganization: 'UC Merced',
      attendeeTitle: 'Director',
      attendeeSecondaryEmail: 'ada@personal.example',
      attendeePhone: '5551234567',
      phoneCode: '123456',
      phoneCodeSent: true,
      phoneVerified: true,
      onSubmit,
    });

    fireEvent.change(screen.getByLabelText(/First Name/), {target: {value: 'Grace'}});
    expect(props.onFirstNameChange).toHaveBeenCalledWith('Grace');
    fireEvent.change(screen.getByLabelText('Middle Name'), {target: {value: 'B.'}});
    expect(props.onMiddleNameChange).toHaveBeenCalledWith('B.');
    fireEvent.change(screen.getByLabelText(/Last Name/), {target: {value: 'Hopper'}});
    expect(props.onLastNameChange).toHaveBeenCalledWith('Hopper');
    fireEvent.click(screen.getByRole('button', {name: 'Individual'}));
    expect(props.onOrgTypeChange).toHaveBeenCalledWith('individual');
    fireEvent.change(screen.getByLabelText(/Title/), {target: {value: 'CEO'}});
    expect(props.onTitleChange).toHaveBeenCalledWith('CEO');
    fireEvent.change(screen.getByLabelText('Secondary Email'), {target: {value: 'other@example.com'}});
    expect(props.onSecondaryEmailChange).toHaveBeenCalledWith('other@example.com');
    fireEvent.change(screen.getByDisplayValue('+1 United States'), {target: {value: '44-GB'}});
    expect(props.onPhoneRegionChange).toHaveBeenCalledWith('44-GB');
    fireEvent.focus(screen.getByLabelText(/Phone Number/));
    fireEvent.change(screen.getByLabelText(/Phone Number/), {target: {value: '(555) 222-3333'}});
    expect(props.onPhoneChange).toHaveBeenCalledWith('5552223333');
    fireEvent.blur(screen.getByLabelText(/Phone Number/));
    fireEvent.change(screen.getByLabelText(/Why attend/), {target: {value: 'Networking'}});
    expect(props.onAnswerChange).toHaveBeenCalledWith('q1', 'Networking');
    fireEvent.click(screen.getByLabelText('VIP'));
    expect(props.onTicketChange).toHaveBeenCalledWith('ticket-2');

    fireEvent.submit(screen.getByRole('button', {name: 'Register'}).closest('form')!);
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('shows validation errors for organization, ticket, phone, duplicate email, and required answers', () => {
    const options: EventRegistrationOptions = {
      ...baseOptions,
      allow_secondary_email: true,
      collect_phone: true,
      verify_phone: true,
      questions: [{id: 'q1', text: 'Why attend?', is_required: true, order: 1}],
    };
    const onSubmit = vi.fn();

    renderForm({
      options,
      selectedTicketId: null,
      answers: {},
      attendeeOrgType: 'organization',
      attendeeOrganization: '',
      attendeeSecondaryEmail: 'ADA@example.com',
      attendeePhone: '5551234567',
      phoneVerified: false,
      primaryEmail: 'ada@example.com',
      onSubmit,
    });

    fireEvent.submit(screen.getByRole('button', {name: 'Register'}).closest('form')!);

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Organization name is required.')).toBeInTheDocument();
    expect(screen.getByText('Please select a ticket.')).toBeInTheDocument();
    expect(screen.getByText('Secondary email must be different from the primary email.')).toBeInTheDocument();
    expect(screen.getByText('Phone number must be verified.')).toBeInTheDocument();
    expect(screen.getByText('This field is required.')).toBeInTheDocument();
  });

  it('handles phone verification controls and phone API errors', () => {
    const options: EventRegistrationOptions = {
      ...baseOptions,
      collect_phone: true,
      verify_phone: true,
    };
    const props = renderForm({
      options,
      attendeePhone: '5551234567',
      phoneCode: '123456',
      phoneCodeSent: true,
      phoneError: null,
      phoneSending: false,
      verifyingPhone: false,
    });

    fireEvent.click(screen.getByRole('button', {name: 'Resend'}));
    expect(props.onSendPhoneCode).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {
      target: {value: '12ab345678'},
    });
    expect(props.onPhoneCodeChange).toHaveBeenCalledWith('123456');
    fireEvent.click(screen.getByRole('button', {name: 'Verify'}));
    expect(props.onVerifyPhoneCode).toHaveBeenCalledTimes(1);
  });
});
