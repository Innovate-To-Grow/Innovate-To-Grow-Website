import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {SubscribePage} from '@/routes/subscription/SubscribePage/page/SubscribePage';
import {emailSignIn, phoneSignIn, profileData} from '@/__tests__/routes/subscription/SubscribePage/fixtures/subscribePageFixtures';

const mockUseAuth = vi.fn();
const mockGetProfile = vi.fn();
const mockGetStoredSession = vi.fn();
const mockIsCurrentSession = vi.fn();
const mockUpdateProfileFields = vi.fn();
const mockGetContactEmails = vi.fn();
const mockGetContactPhones = vi.fn();
const mockUpdateContactEmail = vi.fn();
const mockUpdateContactPhone = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
    getProfile: (...args: unknown[]) => mockGetProfile(...args),
    getStoredSession: () => mockGetStoredSession(),
    isCurrentSession: (...args: unknown[]) => mockIsCurrentSession(...args),
    updateProfileFields: (...args: unknown[]) => mockUpdateProfileFields(...args),
    getContactEmails: (...args: unknown[]) => mockGetContactEmails(...args),
    getContactPhones: (...args: unknown[]) => mockGetContactPhones(...args),
    updateContactEmail: (...args: unknown[]) => mockUpdateContactEmail(...args),
    updateContactPhone: (...args: unknown[]) => mockUpdateContactPhone(...args),
  };
});

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
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
  requestPhoneAuthCode: vi.fn().mockResolvedValue({message: 'ok'}),
  verifyPhoneAuthCode: vi.fn().mockResolvedValue({
    access: 'jwt',
    refresh: 'jwt-r',
    user: {member_uuid: 'uuid-1', phone: '+12025550123'},
    requires_profile_completion: false,
  }),
};

describe('SubscribePage', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mockUseAuth.mockReset();
    mockGetProfile.mockReset();
    mockGetStoredSession.mockReset();
    mockIsCurrentSession.mockReset();
    mockUpdateProfileFields.mockReset();
    mockGetContactEmails.mockReset();
    mockGetContactPhones.mockReset();
    mockUpdateContactEmail.mockReset();
    mockUpdateContactPhone.mockReset();
    baseAuth.clearError.mockReset();
    baseAuth.clearProfileCompletionRequirement.mockReset();
    baseAuth.clearProfileCompletionRequirement.mockReturnValue(true);
    baseAuth.requestEmailAuthCode.mockReset().mockResolvedValue({message: 'ok'});
    baseAuth.verifyEmailAuthCode.mockReset().mockResolvedValue(emailSignIn());
    baseAuth.requestPhoneAuthCode.mockReset().mockResolvedValue({message: 'ok'});
    baseAuth.verifyPhoneAuthCode.mockReset().mockResolvedValue(phoneSignIn());

    mockGetProfile.mockResolvedValue(profileData);
    mockGetStoredSession.mockReturnValue({
      generation: 'generation-a',
      refresh: 'refresh-a',
    });
    mockIsCurrentSession.mockReturnValue(true);
    mockGetContactEmails.mockResolvedValue([]);
    mockGetContactPhones.mockResolvedValue([]);
    mockUseAuth.mockReturnValue({...baseAuth});
  });

  it('shows email step for unauthenticated users', () => {
    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    expect(screen.getByLabelText('Email or Phone')).toBeInTheDocument();
  });

  it('transitions from email to code step on submit', async () => {
    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);

    await waitFor(() => {
      expect(baseAuth.requestEmailAuthCode).toHaveBeenCalledWith('test@example.com', 'subscribe');
    });

    expect(await screen.findByLabelText('Verification Code')).toBeInTheDocument();
  });

  it('routes a phone entry to the SMS-code flow with the subscribe source', async () => {
    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: '(202) 555-0123'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);

    await waitFor(() => {
      expect(baseAuth.requestPhoneAuthCode).toHaveBeenCalledWith('2025550123', '1-US', 'subscribe');
    });
    expect(baseAuth.requestEmailAuthCode).not.toHaveBeenCalled();
  });

  it('transitions from code to profile step when profile is incomplete', async () => {
    const authState = {
      ...baseAuth,
      user: null as {member_uuid: string; email: string} | null,
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
    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);
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
});
