import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {AccountPage} from '@/features/auth/components/pages/AccountPage';
import {profile} from '@/__tests__/features/auth/components/pages/accountPageFixtures';

const mocks = vi.hoisted(() => ({
  useAccountDashboard: vi.fn(),
}));

vi.mock('@/features/auth/components/pages/account/dashboard/useAccountDashboard', () => ({
  useAccountDashboard: () => mocks.useAccountDashboard(),
}));

vi.mock('@/features/auth/components/sections/email/EmailCenter', () => ({
  EmailCenter: () => <div data-testid="email-center" />,
}));

vi.mock('@/features/auth/components/sections/phone/PhoneCenter', () => ({
  PhoneCenter: () => <div data-testid="phone-center" />,
}));

vi.mock('@/features/auth/components/sections/sharedLinks/MySharedLinksSection', () => ({
  MySharedLinksSection: () => <div data-testid="shared-links" />,
}));

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
          secondary_email_verified: false,
          phone_verification_required: false,
          attendee_organization: 'Acme',
          registered_at: '2026-05-01T12:00:00Z',
          ticket_email_sent_at: null,
          ticket_email_error: '',
          barcode_format: 'PDF417',
          barcode_image: 'data:image/png;base64,test',
          event: {id: 'event-1', name: 'Spring Showcase', slug: 'spring', date: '2099-05-01', location: 'Campus', description: ''},
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
