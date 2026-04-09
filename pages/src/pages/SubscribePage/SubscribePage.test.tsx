import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

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
  requestEmailAuthCode: vi.fn().mockResolvedValue({message: 'ok', flow: 'register', next_step: 'verify_code'}),
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
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockGetProfile.mockReset();
    mockUpdateProfileFields.mockReset();

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
      expect(baseAuth.requestEmailAuthCode).toHaveBeenCalledWith('test@example.com');
    });

    expect(await screen.findByLabelText('Verification Code')).toBeInTheDocument();
  });

  it('transitions from code to profile step when profile is incomplete', async () => {
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
      expect(baseAuth.verifyEmailAuthCode).toHaveBeenCalledWith('test@example.com', '123456');
    });

    expect(await screen.findByText(/complete your profile/i)).toBeInTheDocument();
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
    mockUpdateProfileFields.mockResolvedValue({...profileData, email: 'test@example.com', email_subscribe: true});
    mockGetProfile.mockResolvedValue({...profileData, email: 'test@example.com', email_subscribe: true});

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
    await screen.findByText(/complete your profile/i);

    fireEvent.change(screen.getByLabelText(/first name/i), {target: {value: 'Ada'}});
    const orgInputs = screen.getAllByPlaceholderText('Company or organization name');
    fireEvent.change(orgInputs[0], {target: {value: 'Acme Corp'}});
    fireEvent.submit(screen.getByLabelText(/first name/i).closest('form')!);

    await waitFor(() => {
      expect(mockUpdateProfileFields).toHaveBeenCalledWith({
        first_name: 'Ada',
        middle_name: '',
        last_name: '',
        organization: 'Acme Corp',
        title: '',
        email_subscribe: true,
      });
    });
  });
});
