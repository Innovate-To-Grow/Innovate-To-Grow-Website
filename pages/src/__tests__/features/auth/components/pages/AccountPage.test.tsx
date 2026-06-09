import {fireEvent, render, screen} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {AccountPage} from '@/features/auth/components/pages/AccountPage';

const mockUseAccountDashboard = vi.fn();

vi.mock('@/features/auth/components/pages/account/useAccountDashboard', () => ({
  useAccountDashboard: () => mockUseAccountDashboard(),
}));

vi.mock('@/features/auth/components/pages/account/ProfileSection', () => ({
  ProfileSection: (props: {
    onOrganizationTypeChange: (value: string) => void;
    onRetryProfile: () => void;
    onStartEditing: () => void;
    onCancelEditing: () => void;
  }) => (
    <section aria-label="Profile section">
      <button type="button" onClick={() => props.onOrganizationTypeChange('individual')}>
        Switch Individual
      </button>
      <button type="button" onClick={props.onRetryProfile}>
        Retry Profile
      </button>
      <button type="button" onClick={props.onStartEditing}>
        Edit Profile
      </button>
      <button type="button" onClick={props.onCancelEditing}>
        Cancel Profile Edit
      </button>
    </section>
  ),
}));

vi.mock('@/features/auth/components/pages/account/TicketsSection', () => ({
  TicketsSection: (props: {onResendTicketEmail: (registrationId: string) => void}) => (
    <section aria-label="Tickets section">
      <button type="button" onClick={() => props.onResendTicketEmail('registration-1')}>
        Resend Ticket
      </button>
    </section>
  ),
}));

vi.mock('@/features/auth/components/pages/account/DetailsSection', () => ({
  DetailsSection: (props: {displayEmail: string; dateJoined?: string}) => (
    <section aria-label="Details section">
      {props.displayEmail} {props.dateJoined}
    </section>
  ),
}));

vi.mock('@/features/auth/components/pages/account/PasswordSection', () => ({
  PasswordSection: (props: {
    onPasswordRequestCode: () => void;
    onPasswordVerifyCode: () => void;
    onPasswordConfirm: () => void;
  }) => (
    <section aria-label="Password section">
      <button type="button" onClick={props.onPasswordRequestCode}>
        Request Password Code
      </button>
      <button type="button" onClick={props.onPasswordVerifyCode}>
        Verify Password Code
      </button>
      <button type="button" onClick={props.onPasswordConfirm}>
        Confirm Password
      </button>
    </section>
  ),
}));

vi.mock('@/features/auth/components/pages/account/DeleteAccountSection', () => ({
  DeleteAccountSection: (props: {
    onDeleteRequestCode: () => void;
    onDeleteVerifyCode: () => void;
    onDeleteConfirm: () => void;
  }) => (
    <section aria-label="Delete account section">
      <button type="button" onClick={props.onDeleteRequestCode}>
        Request Delete Code
      </button>
      <button type="button" onClick={props.onDeleteVerifyCode}>
        Verify Delete Code
      </button>
      <button type="button" onClick={props.onDeleteConfirm}>
        Confirm Delete
      </button>
    </section>
  ),
}));

vi.mock('@/features/auth/components/sections/EmailCenter', () => ({
  EmailCenter: () => <section aria-label="Email center">Email center</section>,
}));

vi.mock('@/features/auth/components/sections/PhoneCenter', () => ({
  PhoneCenter: () => <section aria-label="Phone center">Phone center</section>,
}));

vi.mock('@/features/auth/components/sections/MySharedLinksSection', () => ({
  MySharedLinksSection: () => <section aria-label="Shared links">Shared links</section>,
}));

const profile = {
  member_uuid: 'member-1',
  email: 'ada@example.com',
  email_verified: true,
  primary_email_id: null,
  first_name: 'Ada',
  middle_name: '',
  last_name: 'Lovelace',
  organization: 'UC Merced',
  title: 'Engineer',
  email_subscribe: true,
  is_staff: false,
  is_active: true,
  date_joined: '2026-01-02',
};

const createAccount = () => ({
  canRender: true,
  profileLoading: false,
  firstName: 'Ada',
  middleName: '',
  lastName: 'Lovelace',
  organizationType: 'organization',
  organization: 'UC Merced',
  title: 'Engineer',
  profileImage: '',
  imageUploading: false,
  imageError: null,
  profileSaving: false,
  profileMessage: null,
  profileError: null,
  isEditingProfile: false,
  handleImageChange: vi.fn(),
  handleProfileSubmit: vi.fn(),
  setFirstName: vi.fn(),
  setMiddleName: vi.fn(),
  setLastName: vi.fn(),
  setOrganizationType: vi.fn(),
  setOrganization: vi.fn(),
  setTitle: vi.fn(),
  loadProfile: vi.fn(),
  setIsEditingProfile: vi.fn(),
  handleCancelEditing: vi.fn(),
  tickets: [],
  liveEventOptions: null,
  ticketsLoading: false,
  liveEventLoading: false,
  resendingId: null,
  handleResendTicketEmail: vi.fn(),
  profile,
  setProfile: vi.fn(),
  displayEmail: 'ada@example.com',
  passwordCodeRequested: false,
  passwordCode: '',
  passwordVerificationToken: null,
  newPassword: '',
  confirmPassword: '',
  passwordLoading: false,
  passwordMessage: null,
  passwordError: null,
  handlePasswordRequestCode: vi.fn(),
  handlePasswordVerifyCode: vi.fn(),
  handlePasswordConfirm: vi.fn(),
  setPasswordCode: vi.fn(),
  setNewPassword: vi.fn(),
  setConfirmPassword: vi.fn(),
  logout: vi.fn(),
  deleteCodeRequested: false,
  deleteCode: '',
  deleteVerificationToken: null,
  deleteLoading: false,
  deleteMessage: null,
  deleteError: null,
  handleDeleteRequestCode: vi.fn(),
  handleDeleteVerifyCode: vi.fn(),
  handleDeleteConfirm: vi.fn(),
  setDeleteCode: vi.fn(),
});

describe('AccountPage', () => {
  beforeEach(() => {
    mockUseAccountDashboard.mockReset();
  });

  it('renders nothing when the dashboard state cannot render', () => {
    mockUseAccountDashboard.mockReturnValue({...createAccount(), canRender: false});

    const {container} = render(<AccountPage />);

    expect(container).toBeEmptyDOMElement();
  });

  it('renders the profile loading state', () => {
    mockUseAccountDashboard.mockReturnValue({...createAccount(), profileLoading: true});

    render(<AccountPage />);

    expect(screen.getByText('Loading profile...')).toBeInTheDocument();
  });

  it('renders the dashboard sections and wires account actions', () => {
    const account = createAccount();
    mockUseAccountDashboard.mockReturnValue(account);

    render(<AccountPage />);

    expect(screen.getByRole('heading', {name: 'Account Dashboard'})).toBeInTheDocument();
    expect(screen.getByLabelText('Email center')).toBeInTheDocument();
    expect(screen.getByLabelText('Phone center')).toBeInTheDocument();
    expect(screen.getByLabelText('Shared links')).toBeInTheDocument();
    expect(screen.getByText(/ada@example.com/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Switch Individual'}));
    expect(account.setOrganizationType).toHaveBeenCalledWith('individual');
    expect(account.setOrganization).toHaveBeenCalledWith('');
    expect(account.setTitle).toHaveBeenCalledWith('');

    fireEvent.click(screen.getByRole('button', {name: 'Retry Profile'}));
    expect(account.loadProfile).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', {name: 'Edit Profile'}));
    expect(account.setIsEditingProfile).toHaveBeenCalledWith(true);

    fireEvent.click(screen.getByRole('button', {name: 'Cancel Profile Edit'}));
    expect(account.handleCancelEditing).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', {name: 'Resend Ticket'}));
    expect(account.handleResendTicketEmail).toHaveBeenCalledWith('registration-1');

    fireEvent.click(screen.getByRole('button', {name: 'Request Password Code'}));
    fireEvent.click(screen.getByRole('button', {name: 'Verify Password Code'}));
    fireEvent.click(screen.getByRole('button', {name: 'Confirm Password'}));
    expect(account.handlePasswordRequestCode).toHaveBeenCalledTimes(1);
    expect(account.handlePasswordVerifyCode).toHaveBeenCalledTimes(1);
    expect(account.handlePasswordConfirm).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', {name: 'Request Delete Code'}));
    fireEvent.click(screen.getByRole('button', {name: 'Verify Delete Code'}));
    fireEvent.click(screen.getByRole('button', {name: 'Confirm Delete'}));
    expect(account.handleDeleteRequestCode).toHaveBeenCalledTimes(1);
    expect(account.handleDeleteVerifyCode).toHaveBeenCalledTimes(1);
    expect(account.handleDeleteConfirm).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', {name: /sign out/i}));
    expect(account.logout).toHaveBeenCalledTimes(1);
  });
});
