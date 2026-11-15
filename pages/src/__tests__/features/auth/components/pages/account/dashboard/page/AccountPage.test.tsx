import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {AccountPage} from '@/features/auth/components/pages/account/dashboard/AccountPage';
import {profile} from '@/__tests__/features/auth/components/pages/account/dashboard/page/accountPageFixtures';

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

    // ProfileSection summarises the profile fields until editing starts.
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText('CEO')).toBeInTheDocument();

    // DetailsSection shows the joined date; the email cards already show the address.
    expect(screen.queryByText('ada@example.com')).not.toBeInTheDocument();
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
});
