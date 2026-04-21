import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {SubscribePage} from './SubscribePage';

const mockUseAuth = vi.fn();
const mockGetProfile = vi.fn();
const mockUpdateProfileFields = vi.fn();

vi.mock('../../components/Auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../components/Auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

vi.mock('../../services/auth', async () => {
  const actual = await vi.importActual<typeof import('../../services/auth')>('../../services/auth');
  return {
    ...actual,
    getProfile: (...args: unknown[]) => mockGetProfile(...args),
    updateProfileFields: (...args: unknown[]) => mockUpdateProfileFields(...args),
  };
});

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  };
});

const baseAuth = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
  clearError: vi.fn(),
  clearProfileCompletionRequirement: vi.fn(),
  requestEmailAuthCode: vi.fn().mockResolvedValue({message: 'ok'}),
  verifyEmailAuthCode: vi.fn().mockResolvedValue({
    access: 'jwt',
    refresh: 'jwt-r',
    user: {member_uuid: 'uuid-1', email: 'test@example.com'},
    requires_profile_completion: true,
  }),
};

const profileData = {
  member_uuid: 'uuid-1',
  email: 'member@example.com',
  email_verified: true,
  primary_email_id: 'eid-1',
  first_name: 'Ada',
  middle_name: '',
  last_name: 'Lovelace',
  organization: 'Individual',
  title: '',
  email_subscribe: false,
  is_staff: false,
  is_active: true,
  date_joined: '2026-01-01',
};

describe('SubscribePage', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mockUseAuth.mockReset();
    mockGetProfile.mockReset();
    mockUpdateProfileFields.mockReset();
    baseAuth.clearError.mockReset();
    baseAuth.clearProfileCompletionRequirement.mockReset();
    baseAuth.requestEmailAuthCode.mockClear();
    baseAuth.verifyEmailAuthCode.mockClear();

    mockGetProfile.mockResolvedValue(profileData);
    mockUseAuth.mockReturnValue({...baseAuth});
  });

  it('shows email step for unauthenticated users', () => {
    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    expect(screen.getByLabelText('Email')).toBeInTheDocument();
  });

  it('transitions from email to code step on submit', async () => {
    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Email'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email').closest('form')!);

    await waitFor(() => {
      expect(baseAuth.requestEmailAuthCode).toHaveBeenCalledWith('test@example.com', 'subscribe');
    });

    expect(await screen.findByLabelText('Verification Code')).toBeInTheDocument();
  });

  it('transitions from code to profile step when profile is incomplete', async () => {
    const authState = {
      ...baseAuth,
      user: null,
      isAuthenticated: false,
      verifyEmailAuthCode: vi.fn().mockImplementation(async () => {
        authState.user = {member_uuid: 'uuid-1', email: 'test@example.com'};
        authState.isAuthenticated = true;
        return {
          access: 'jwt',
          refresh: 'jwt-r',
          user: authState.user,
          requires_profile_completion: true,
        };
      }),
    };
    mockUseAuth.mockImplementation(() => authState);

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    // Go to code step
    fireEvent.change(screen.getByLabelText('Email'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email').closest('form')!);
    await screen.findByLabelText('Verification Code');

    // Submit code
    fireEvent.change(screen.getByLabelText('Verification Code'), {target: {value: '123456'}});
    fireEvent.submit(screen.getByLabelText('Verification Code').closest('form')!);

    await waitFor(() => {
      expect(authState.verifyEmailAuthCode).toHaveBeenCalledWith('test@example.com', '123456');
    });

    await waitFor(() => {
      expect(mockGetProfile).toHaveBeenCalled();
    });

    expect(await screen.findByLabelText(/first name/i)).toBeInTheDocument();
  });

  it('shows manage step directly for authenticated users', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });

    mockGetProfile.mockResolvedValue({...profileData, email_subscribe: true});

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockGetProfile).toHaveBeenCalled();
    });

    // Use getAllBy since strict mode may cause multiple renders
    const emailElements = await screen.findAllByText('member@example.com');
    expect(emailElements.length).toBeGreaterThanOrEqual(1);

    const newsletterLabels = screen.getAllByText('Newsletter');
    expect(newsletterLabels.length).toBeGreaterThanOrEqual(1);
  });

  it('opens directly on the profile step when the query requests it', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });

    mockGetProfile.mockResolvedValue({
      ...profileData,
      organization: 'Acme Corp',
      title: 'Director',
    });

    render(
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
        <SubscribePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockGetProfile).toHaveBeenCalled();
      expect(screen.getAllByLabelText(/first name/i).some((input) => (input as HTMLInputElement).value === 'Ada')).toBe(true);
      expect(screen.getAllByLabelText(/last name/i).some((input) => (input as HTMLInputElement).value === 'Lovelace')).toBe(true);
      expect(
        screen.getAllByPlaceholderText('Company or organization name').some(
          (input) => (input as HTMLInputElement).value === 'Acme Corp',
        ),
      ).toBe(true);
      expect(
        screen.getAllByPlaceholderText('Your title or position (e.g. CEO, Director)').some(
          (input) => (input as HTMLInputElement).value === 'Director',
        ),
      ).toBe(true);
    });
  });

  it('preserves prefilled profile data from the direct link and advances to manage after save', async () => {
    const incompleteProfile = {
      ...profileData,
      last_name: '',
      organization: 'Acme Corp',
      title: 'Director',
    };
    const completedProfile = {
      ...incompleteProfile,
      last_name: 'Lovelace',
      email_subscribe: true,
    };

    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    mockGetProfile
      .mockResolvedValueOnce(incompleteProfile)
      .mockResolvedValue(completedProfile);
    mockUpdateProfileFields.mockResolvedValue(completedProfile);

    render(
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
        <SubscribePage />
      </MemoryRouter>,
    );

    const activeFirstNameInput = await screen.findByLabelText(/first name/i);
    const activeLastNameInput = screen.getByLabelText(/last name/i);
    const activeOrgInput = screen.getByPlaceholderText('Company or organization name');
    const activeTitleInput = screen.getByPlaceholderText('Your title or position (e.g. CEO, Director)');

    expect(activeFirstNameInput).toHaveValue('Ada');
    expect(activeOrgInput).toHaveValue('Acme Corp');
    expect(activeTitleInput).toHaveValue('Director');

    fireEvent.change(activeLastNameInput, {target: {value: 'Lovelace'}});
    fireEvent.submit(activeFirstNameInput.closest('form')!);

    await waitFor(() => {
      expect(mockUpdateProfileFields).toHaveBeenCalledWith({
        first_name: 'Ada',
        middle_name: '',
        last_name: 'Lovelace',
        organization: 'Acme Corp',
        title: 'Director',
        email_subscribe: true,
      });
    });

    expect(await screen.findByText('Manage your email subscription preferences below.')).toBeInTheDocument();
  });

  it('toggles subscription in manage step', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });

    mockGetProfile.mockResolvedValue({...profileData, email_subscribe: true});
    mockUpdateProfileFields.mockResolvedValue({...profileData, email_subscribe: false});

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockGetProfile).toHaveBeenCalled();
    });

    // Wait for the toggle button to appear
    const toggleButtons = await screen.findAllByRole('button', {name: 'Turn off newsletter subscription'});
    fireEvent.click(toggleButtons[0]);

    await waitFor(() => {
      expect(mockUpdateProfileFields).toHaveBeenCalledWith({email_subscribe: false});
    });
  });

  it('saves profile and auto-subscribes in profile step', async () => {
    const authState = {
      ...baseAuth,
      user: null,
      isAuthenticated: false,
      verifyEmailAuthCode: vi.fn().mockImplementation(async () => {
        authState.user = {member_uuid: 'uuid-1', email: 'test@example.com'};
        authState.isAuthenticated = true;
        return {
          access: 'jwt',
          refresh: 'jwt-r',
          user: authState.user,
          requires_profile_completion: true,
        };
      }),
    };
    mockUseAuth.mockImplementation(() => authState);

    mockUpdateProfileFields.mockResolvedValue({
      ...profileData,
      email: 'test@example.com',
      organization: 'Acme Corp',
      title: '',
      email_subscribe: true,
    });
    mockGetProfile.mockResolvedValue({
      ...profileData,
      email: 'test@example.com',
      organization: '',
      title: '',
      email_subscribe: true,
    });

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    // Navigate to code step
    fireEvent.change(screen.getByLabelText('Email'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email').closest('form')!);
    await screen.findByLabelText('Verification Code');

    // Verify code → profile step
    fireEvent.change(screen.getByLabelText('Verification Code'), {target: {value: '123456'}});
    fireEvent.submit(screen.getByLabelText('Verification Code').closest('form')!);
    await waitFor(() => {
      expect(authState.verifyEmailAuthCode).toHaveBeenCalledWith('test@example.com', '123456');
      expect(mockGetProfile).toHaveBeenCalled();
    });

    const firstNameInput = await screen.findByLabelText(/first name/i);
    const lastNameInput = screen.getByLabelText(/last name/i);
    const orgInput = screen.getByPlaceholderText('Company or organization name');

    fireEvent.change(firstNameInput, {target: {value: 'Ada'}});
    fireEvent.change(lastNameInput, {target: {value: 'Lovelace'}});
    fireEvent.change(orgInput, {target: {value: 'Acme Corp'}});
    fireEvent.submit(firstNameInput.closest('form')!);

    await waitFor(() => {
      expect(mockUpdateProfileFields).toHaveBeenCalledWith({
        first_name: 'Ada',
        middle_name: '',
        last_name: 'Lovelace',
        organization: 'Acme Corp',
        title: '',
        email_subscribe: true,
      });
    });

    expect(baseAuth.clearProfileCompletionRequirement).toHaveBeenCalled();
  });
});
