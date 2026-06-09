import {fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {describe, expect, it, vi} from 'vitest';

import {DeleteAccountSection} from '@/features/auth/components/pages/account/DeleteAccountSection';
import {PasswordSection} from '@/features/auth/components/pages/account/PasswordSection';
import {ProfileSection} from '@/features/auth/components/pages/account/ProfileSection';
import {TicketsSection} from '@/features/auth/components/pages/account/TicketsSection';
import type {EventRegistrationOptions, Registration} from '@/features/events/api';

const registration: Registration = {
  id: 'reg-1',
  ticket_code: 'I2G-123',
  attendee_first_name: 'Ada',
  attendee_last_name: 'Lovelace',
  attendee_name: 'Ada Lovelace',
  attendee_email: 'ada@example.com',
  attendee_secondary_email: '',
  attendee_phone: '',
  phone_verified: false,
  phone_verification_required: false,
  attendee_organization: 'UC Merced',
  registered_at: '',
  ticket_email_sent_at: '2026-06-08T10:00:00Z',
  ticket_email_error: '',
  barcode_format: 'png',
  barcode_image: 'data:image/png;base64,abc',
  event: {id: 'event-1', name: 'Demo Day', slug: 'demo', date: '2026-05-01', location: 'Campus', description: 'Demo'},
  ticket: {id: 'ticket-1', name: 'General'},
  answers: [],
};

const liveEvent: EventRegistrationOptions = {
  id: 'event-2',
  name: 'Open Demo',
  slug: 'open-demo',
  date: '2026-06-01',
  location: 'Conference Center',
  description: 'Register now',
  allow_secondary_email: false,
  collect_phone: false,
  verify_phone: false,
  tickets: [],
  questions: [],
  registration: null,
  member_emails: [],
  member_profile: null,
  member_phone: null,
  phone_regions: [],
};

describe('account section components', () => {
  it('renders and edits profile fields', () => {
    const onSubmit = vi.fn((event) => event.preventDefault());
    const onFirstNameChange = vi.fn();
    const onMiddleNameChange = vi.fn();
    const onLastNameChange = vi.fn();
    const onOrganizationTypeChange = vi.fn();
    const onOrganizationChange = vi.fn();
    const onTitleChange = vi.fn();
    const onRetryProfile = vi.fn();
    const onCancelEditing = vi.fn();
    const onImageChange = vi.fn();

    render(
      <ProfileSection
        firstName="Ada"
        middleName=""
        lastName="Lovelace"
        organizationType="organization"
        organization="UC Merced"
        title="Engineer"
        profileImage={null}
        imageUploading={false}
        imageError="Image too large"
        profileSaving={false}
        profileMessage="Profile saved"
        profileError="Profile failed"
        isEditingProfile
        onImageChange={onImageChange}
        onSubmit={onSubmit}
        onFirstNameChange={onFirstNameChange}
        onMiddleNameChange={onMiddleNameChange}
        onLastNameChange={onLastNameChange}
        onOrganizationTypeChange={onOrganizationTypeChange}
        onOrganizationChange={onOrganizationChange}
        onTitleChange={onTitleChange}
        onRetryProfile={onRetryProfile}
        onStartEditing={vi.fn()}
        onCancelEditing={onCancelEditing}
      />,
    );

    expect(screen.getByText('AL')).toBeInTheDocument();
    expect(screen.getByText('Profile saved')).toBeInTheDocument();
    expect(screen.getByText('Profile failed')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('First Name'), {target: {value: 'Augusta'}});
    expect(onFirstNameChange).toHaveBeenCalledWith('Augusta');
    fireEvent.change(screen.getByLabelText('Middle Name'), {target: {value: 'Byron'}});
    expect(onMiddleNameChange).toHaveBeenCalledWith('Byron');
    fireEvent.change(screen.getByLabelText('Last Name'), {target: {value: 'King'}});
    expect(onLastNameChange).toHaveBeenCalledWith('King');
    fireEvent.click(screen.getByRole('button', {name: 'Individual'}));
    expect(onOrganizationTypeChange).toHaveBeenCalledWith('individual');
    fireEvent.change(screen.getByPlaceholderText('Company or organization name'), {target: {value: 'NASA'}});
    expect(onOrganizationChange).toHaveBeenCalledWith('NASA');
    fireEvent.change(screen.getByLabelText(/Title/), {target: {value: 'Director'}});
    expect(onTitleChange).toHaveBeenCalledWith('Director');
    fireEvent.click(screen.getByRole('button', {name: 'Retry'}));
    expect(onRetryProfile).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
    expect(onCancelEditing).toHaveBeenCalledTimes(1);
    fireEvent.change(document.querySelector('#profile-image-upload') as HTMLInputElement, {
      target: {files: [new File(['avatar'], 'avatar.png', {type: 'image/png'})]},
    });
    expect(onImageChange).toHaveBeenCalledTimes(1);
    fireEvent.submit(screen.getByRole('button', {name: 'Save Profile'}).closest('form')!);
    expect(onSubmit).toHaveBeenCalled();
  });

  it('renders read-only profile state with uploaded image and edit action', () => {
    const onStartEditing = vi.fn();

    render(
      <ProfileSection
        firstName="Ada"
        middleName=""
        lastName="Lovelace"
        organizationType="individual"
        organization=""
        title=""
        profileImage="/avatar.png"
        imageUploading
        imageError="<p>unsafe</p>"
        profileSaving={false}
        profileMessage={null}
        profileError={null}
        isEditingProfile={false}
        onImageChange={vi.fn()}
        onSubmit={vi.fn()}
        onFirstNameChange={vi.fn()}
        onMiddleNameChange={vi.fn()}
        onLastNameChange={vi.fn()}
        onOrganizationTypeChange={vi.fn()}
        onOrganizationChange={vi.fn()}
        onTitleChange={vi.fn()}
        onRetryProfile={vi.fn()}
        onStartEditing={onStartEditing}
        onCancelEditing={vi.fn()}
      />,
    );

    expect(screen.getByRole('img', {name: 'Profile'})).toHaveAttribute('src', '/avatar.png');
    expect(screen.queryByText('unsafe')).toBeNull();
    expect(screen.getByLabelText('First Name')).toBeDisabled();
    expect(screen.queryByPlaceholderText('Company or organization name')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Edit Profile'}));
    expect(onStartEditing).toHaveBeenCalledTimes(1);
  });

  it('renders password verification and confirmation states', () => {
    const request = vi.fn();
    const verify = vi.fn((event) => event.preventDefault());
    const confirm = vi.fn((event) => event.preventDefault());
    const onPasswordCodeChange = vi.fn();
    const onNewPasswordChange = vi.fn();
    const onConfirmPasswordChange = vi.fn();

    const {rerender} = render(
      <PasswordSection
        passwordCodeRequested={false}
        passwordCode=""
        passwordVerificationToken={null}
        newPassword=""
        confirmPassword=""
        passwordLoading={false}
        passwordMessage={null}
        passwordError={null}
        onPasswordRequestCode={request}
        onPasswordVerifyCode={verify}
        onPasswordConfirm={confirm}
        onPasswordCodeChange={onPasswordCodeChange}
        onNewPasswordChange={onNewPasswordChange}
        onConfirmPasswordChange={onConfirmPasswordChange}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: 'Send Code'}));
    expect(request).toHaveBeenCalledTimes(1);

    rerender(
      <PasswordSection
        passwordCodeRequested
        passwordCode="123456"
        passwordVerificationToken={null}
        newPassword=""
        confirmPassword=""
        passwordLoading={false}
        passwordMessage="Code sent"
        passwordError="Bad code"
        onPasswordRequestCode={request}
        onPasswordVerifyCode={verify}
        onPasswordConfirm={confirm}
        onPasswordCodeChange={onPasswordCodeChange}
        onNewPasswordChange={onNewPasswordChange}
        onConfirmPasswordChange={onConfirmPasswordChange}
      />,
    );
    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '654321'}});
    expect(onPasswordCodeChange).toHaveBeenCalledWith('654321');
    fireEvent.submit(screen.getByRole('button', {name: 'Verify Code'}).closest('form')!);
    expect(verify).toHaveBeenCalled();

    rerender(
      <PasswordSection
        passwordCodeRequested={false}
        passwordCode=""
        passwordVerificationToken="token"
        newPassword="password123"
        confirmPassword="password123"
        passwordLoading={false}
        passwordMessage={null}
        passwordError={null}
        onPasswordRequestCode={request}
        onPasswordVerifyCode={verify}
        onPasswordConfirm={confirm}
        onPasswordCodeChange={onPasswordCodeChange}
        onNewPasswordChange={onNewPasswordChange}
        onConfirmPasswordChange={onConfirmPasswordChange}
      />,
    );
    fireEvent.change(screen.getByLabelText('New Password'), {target: {value: 'password456'}});
    expect(onNewPasswordChange).toHaveBeenCalledWith('password456');
    fireEvent.change(screen.getByLabelText('Confirm Password'), {target: {value: 'password456'}});
    expect(onConfirmPasswordChange).toHaveBeenCalledWith('password456');
    fireEvent.submit(screen.getByRole('button', {name: 'Change Password'}).closest('form')!);
    expect(confirm).toHaveBeenCalled();
  });

  it('renders delete-account states after expansion', () => {
    const request = vi.fn();
    const verify = vi.fn((event) => event.preventDefault());
    const confirm = vi.fn((event) => event.preventDefault());
    const {rerender} = render(
      <DeleteAccountSection
        deleteCodeRequested={false}
        deleteCode=""
        deleteVerificationToken={null}
        deleteLoading={false}
        deleteMessage={null}
        deleteError={null}
        onDeleteRequestCode={request}
        onDeleteVerifyCode={verify}
        onDeleteConfirm={confirm}
        onDeleteCodeChange={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: /Delete Account/}));
    fireEvent.click(screen.getByRole('button', {name: 'Send Deletion Code'}));
    expect(request).toHaveBeenCalledTimes(1);

    rerender(
      <DeleteAccountSection
        deleteCodeRequested
        deleteCode="123456"
        deleteVerificationToken={null}
        deleteLoading={false}
        deleteMessage="Code sent"
        deleteError="Bad code"
        onDeleteRequestCode={request}
        onDeleteVerifyCode={verify}
        onDeleteConfirm={confirm}
        onDeleteCodeChange={vi.fn()}
      />,
    );
    fireEvent.submit(screen.getByRole('button', {name: 'Verify Code'}).closest('form')!);
    expect(verify).toHaveBeenCalled();

    rerender(
      <DeleteAccountSection
        deleteCodeRequested={false}
        deleteCode=""
        deleteVerificationToken="token"
        deleteLoading={false}
        deleteMessage={null}
        deleteError={null}
        onDeleteRequestCode={request}
        onDeleteVerifyCode={verify}
        onDeleteConfirm={confirm}
        onDeleteCodeChange={vi.fn()}
      />,
    );
    fireEvent.submit(screen.getAllByRole('button', {name: 'Delete Account'}).at(-1)!.closest('form')!);
    expect(confirm).toHaveBeenCalled();
  });

  it('renders ticket loading, open registration, and ticket cards', () => {
    const resend = vi.fn();
    const loading = render(
      <TicketsSection tickets={[]} liveEvent={null} ticketsLoading liveEventLoading={false} resendingId={null} onResendTicketEmail={resend} />,
    );
    expect(screen.getByText('Loading registrations...')).toBeInTheDocument();
    loading.unmount();

    render(
      <MemoryRouter>
        <TicketsSection
          tickets={[registration]}
          liveEvent={liveEvent}
          ticketsLoading={false}
          liveEventLoading={false}
          resendingId="reg-1"
          onResendTicketEmail={resend}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText('Open Demo')).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'Register for this event'})).toHaveAttribute('href', '/event-registration');
    expect(screen.getByText('Demo Day')).toBeInTheDocument();
    expect(screen.getByText('I2G-123')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Sending...'})).toBeDisabled();
  });
});
