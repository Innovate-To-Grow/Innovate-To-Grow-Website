import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';

import {RegistrationFormStep} from './RegistrationFormStep';

describe('RegistrationFormStep', () => {
  it('blocks submission and shows a last-name error when last name is blank', () => {
    const onSubmit = vi.fn();

    render(
      <RegistrationFormStep
        options={{
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
        }}
        selectedTicketId="ticket-1"
        answers={{}}
        submitting={false}
        attendeeFirstName="Ada"
        attendeeMiddleName=""
        attendeeLastName=""
        attendeeOrgType="individual"
        attendeeOrganization=""
        attendeeTitle=""
        attendeeSecondaryEmail=""
        attendeePhone=""
        primaryEmail="ada@example.com"
        phoneError={null}
        phoneRegion="1-US"
        onFirstNameChange={vi.fn()}
        onMiddleNameChange={vi.fn()}
        onLastNameChange={vi.fn()}
        onOrgTypeChange={vi.fn()}
        onOrganizationChange={vi.fn()}
        onTitleChange={vi.fn()}
        onTicketChange={vi.fn()}
        onAnswerChange={vi.fn()}
        onSecondaryEmailChange={vi.fn()}
        onPhoneChange={vi.fn()}
        onPhoneRegionChange={vi.fn()}
        phoneCode=""
        phoneCodeSent={false}
        phoneSending={false}
        phoneVerified={false}
        verifyingPhone={false}
        onPhoneCodeChange={vi.fn()}
        onSendPhoneCode={vi.fn()}
        onVerifyPhoneCode={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.submit(screen.getByRole('button', {name: 'Register'}).closest('form')!);

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Last name is required.')).toBeInTheDocument();
  });
});
