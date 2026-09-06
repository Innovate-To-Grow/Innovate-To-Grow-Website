import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type {ProfileResponse} from '@/features/auth/api';
import {AccountPage} from '@/features/auth/components/pages/AccountPage';

const mocks = vi.hoisted(() => ({
  useAccountDashboard: vi.fn(),
}));

vi.mock('@/features/auth/components/pages/account/useAccountDashboard', () => ({
  useAccountDashboard: () => mocks.useAccountDashboard(),
}));

vi.mock('@/features/auth/components/sections/EmailCenter', () => ({
  EmailCenter: () => <div data-testid="email-center" />,
}));

vi.mock('@/features/auth/components/sections/PhoneCenter', () => ({
  PhoneCenter: () => <div data-testid="phone-center" />,
}));

vi.mock('@/features/auth/components/sections/MySharedLinksSection', () => ({
  MySharedLinksSection: () => <div data-testid="shared-links" />,
}));

const profile = (): ProfileResponse => ({
  member_uuid: 'm-1',
  email: 'ada@example.com',
  email_verified: true,
  primary_email_id: 'pe-1',
  first_name: 'Ada',
  middle_name: '',
  last_name: 'Lovelace',
  organization: 'Acme Corp',
  title: 'CEO',
  email_subscribe: true,
  is_staff: false,
  is_active: true,
  date_joined: '2026-01-01T00:00:00Z',
});

const account = (overrides: Record<string, unknown> = {}) => ({
  canRender: true,
  profileLoading: false,
  displayEmail: 'ada@example.com',
  imageError: null,
  imageUploading: false,
  isEditingProfile: false,
  logout: vi.fn(),
  organization: 'Acme Corp',
  organizationType: 'organization',
  title: 'CEO',
  profile: profile(),
  profileError: null,
  profileImage: null,
  profileMessage: null,
  profileSaving: false,
  passwordCodeRequested: false,
  passwordCode: '',
  passwordVerificationToken: null,
  newPassword: '',
  confirmPassword: '',
  passwordLoading: false,
  passwordMessage: null,
  passwordError: null,
  passwordChannel: null,
  deleteCodeRequested: false,
  deleteCode: '',
  deleteVerificationToken: null,
  deleteLoading: false,
  deleteMessage: null,
  deleteError: null,
  resendingId: null,
  firstName: 'Ada',
  lastName: 'Lovelace',
  middleName: '',
  tickets: [],
  ticketsLoading: false,
  registrationEvents: [],
  registrationEventsLoading: false,
  setProfile: vi.fn(),
  setFirstName: vi.fn(),
  setMiddleName: vi.fn(),
  setLastName: vi.fn(),
  setPasswordCode: vi.fn(),
  setNewPassword: vi.fn(),
  setConfirmPassword: vi.fn(),
  setDeleteCode: vi.fn(),
  setOrganization: vi.fn(),
  setOrganizationType: vi.fn(),
  setTitle: vi.fn(),
  setIsEditingProfile: vi.fn(),
  handlePasswordConfirm: vi.fn(),
  handlePasswordRequestCode: vi.fn(),
  handlePasswordVerifyCode: vi.fn(),
  handleDeleteRequestCode: vi.fn(),
  handleDeleteVerifyCode: vi.fn(),
  handleDeleteConfirm: vi.fn(),
  handleCancelEditing: vi.fn(),
  handleImageChange: vi.fn(),
  handleProfileSubmit: vi.fn(),
  handleResendTicketEmail: vi.fn(),
  loadProfile: vi.fn(),
  ...overrides,
});

describe('AccountPage', () => {
  beforeEach(() => {
    mocks.useAccountDashboard.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders nothing while the dashboard cannot render', () => {
    mocks.useAccountDashboard.mockReturnValue(account({canRender: false}));

    const {container} = render(
      <MemoryRouter>
        <AccountPage />
      </MemoryRouter>,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('shows the profile loading state', () => {
    mocks.useAccountDashboard.mockReturnValue(account({profileLoading: true}));

    render(
      <MemoryRouter>
        <AccountPage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Loading profile...')).toBeInTheDocument();
    expect(screen.queryByRole('heading', {name: 'Account Dashboard'})).not.toBeInTheDocument();
  });

  it('wires dashboard state into each section', () => {
    const accountValue = account();
    mocks.useAccountDashboard.mockReturnValue(accountValue);

    render(
      <MemoryRouter>
        <AccountPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', {name: 'Account Dashboard'})).toBeInTheDocument();

    // ProfileSection receives the editable field values.
    expect(screen.getByDisplayValue('Ada')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Lovelace')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Acme Corp')).toBeInTheDocument();
    expect(screen.getByDisplayValue('CEO')).toBeInTheDocument();

    // DetailsSection receives the display email and joined date.
    expect(screen.getByText('ada@example.com')).toBeInTheDocument();
    expect(screen.getByText('Member Since')).toBeInTheDocument();

    // Password / delete sections render their headers.
    expect(screen.getByRole('heading', {name: 'Change Password'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Delete Account'})).toBeInTheDocument();

    // Email / phone / shared links render when a profile exists.
    expect(screen.getByTestId('email-center')).toBeInTheDocument();
    expect(screen.getByTestId('phone-center')).toBeInTheDocument();
    expect(screen.getByTestId('shared-links')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Edit Profile'}));
    expect(accountValue.setIsEditingProfile).toHaveBeenCalledWith(true);

    fireEvent.click(screen.getByRole('button', {name: 'Sign Out'}));
    expect(accountValue.logout).toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', {name: 'Send Code'}));
    expect(accountValue.handlePasswordRequestCode).toHaveBeenCalled();
  });

  it('omits the email and phone centers when there is no profile', () => {
    mocks.useAccountDashboard.mockReturnValue(account({profile: null, displayEmail: 'member@example.com'}));

    render(
      <MemoryRouter>
        <AccountPage />
      </MemoryRouter>,
    );

    expect(screen.queryByTestId('email-center')).not.toBeInTheDocument();
    expect(screen.queryByTestId('phone-center')).not.toBeInTheDocument();
    expect(screen.getByTestId('shared-links')).toBeInTheDocument();
    expect(screen.getByText('member@example.com')).toBeInTheDocument();
  });

  it('wires the organization toggle and ticket resend callbacks', () => {
    const accountValue = account({
      isEditingProfile: true,
      tickets: [
        {
          id: 'reg-1',
          ticket_code: 'I2G-1',
          attendee_first_name: 'Ada',
          attendee_last_name: 'Lovelace',
          attendee_name: 'Ada Lovelace',
          attendee_email: 'ada@example.com',
          attendee_secondary_email: '',
          attendee_phone: '',
          phone_verified: false,
          phone_verification_required: false,
          attendee_organization: 'Acme',
          registered_at: '2026-05-01T12:00:00Z',
          ticket_email_sent_at: null,
          ticket_email_error: '',
          barcode_format: 'PDF417',
          barcode_image: 'data:image/png;base64,test',
          event: {id: 'event-1', name: 'Spring Showcase', slug: 'spring', date: '2026-05-01', location: 'Campus', description: ''},
          ticket: {id: 'ticket-1', name: 'General Admission'},
          answers: [],
        },
      ],
    });
    mocks.useAccountDashboard.mockReturnValue(accountValue);

    render(
      <MemoryRouter>
        <AccountPage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', {name: 'Individual'}));
    expect(accountValue.setOrganizationType).toHaveBeenCalledWith('individual');
    expect(accountValue.setOrganization).toHaveBeenCalledWith('');
    expect(accountValue.setTitle).toHaveBeenCalledWith('');

    fireEvent.click(screen.getByRole('button', {name: 'Resend Ticket Email'}));
    expect(accountValue.handleResendTicketEmail).toHaveBeenCalledWith('reg-1');
  });

  it('wires the profile retry callback', () => {
    const accountValue = account({profileError: 'Failed to load'});
    mocks.useAccountDashboard.mockReturnValue(accountValue);

    render(
      <MemoryRouter>
        <AccountPage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', {name: 'Retry'}));
    expect(accountValue.loadProfile).toHaveBeenCalled();
  });
});
