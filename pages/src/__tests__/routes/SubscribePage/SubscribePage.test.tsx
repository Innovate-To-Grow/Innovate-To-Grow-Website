import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {SubscribePage} from '@/routes/SubscribePage/SubscribePage';

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
    baseAuth.verifyEmailAuthCode.mockReset().mockResolvedValue({
      access: 'jwt',
      refresh: 'jwt-r',
      user: {member_uuid: 'uuid-1', email: 'test@example.com'},
      requires_profile_completion: true,
    });
    baseAuth.requestPhoneAuthCode.mockReset().mockResolvedValue({message: 'ok'});
    baseAuth.verifyPhoneAuthCode.mockReset().mockResolvedValue({
      access: 'jwt',
      refresh: 'jwt-r',
      user: {member_uuid: 'uuid-1', phone: '+12025550123'},
      requires_profile_completion: false,
    });

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

  it('shows an error for an invalid email or phone entry', async () => {
    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'not-an-email'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);

    expect(
      await screen.findByText('Please enter a valid email address or 10-digit US phone number.'),
    ).toBeInTheDocument();
    expect(baseAuth.requestEmailAuthCode).not.toHaveBeenCalled();
    expect(baseAuth.requestPhoneAuthCode).not.toHaveBeenCalled();
  });

  it('surfaces an auth-code error from the email submit', async () => {
    baseAuth.requestEmailAuthCode.mockRejectedValueOnce({response: {data: {detail: 'Rate limited.'}}});

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);

    expect(await screen.findByText('Rate limited.')).toBeInTheDocument();
  });

  it('lands on manage when the verified account already has a complete profile', async () => {
    baseAuth.verifyEmailAuthCode.mockResolvedValueOnce({
      access: 'jwt',
      refresh: 'jwt-r',
      user: {member_uuid: 'uuid-1', email: 'test@example.com'},
      requires_profile_completion: false,
    });

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);
    const codeInput = await screen.findByLabelText('Verification Code');
    fireEvent.change(codeInput, {target: {value: '123456'}});
    fireEvent.submit(codeInput.closest('form')!);

    expect(
      await screen.findByText('Manage your email and text message subscription preferences below.'),
    ).toBeInTheDocument();
  });

  it('shows a verify error from the code submit', async () => {
    baseAuth.verifyEmailAuthCode.mockRejectedValueOnce({response: {data: {code: ['Expired.']}}});

    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);
    const codeInput = await screen.findByLabelText('Verification Code');
    fireEvent.change(codeInput, {target: {value: '123456'}});
    fireEvent.submit(codeInput.closest('form')!);

    expect(await screen.findByText('Expired.')).toBeInTheDocument();
  });

  it('resends the email code and surfaces resend errors', async () => {
    vi.useFakeTimers();
    try {
      baseAuth.requestEmailAuthCode
        .mockResolvedValueOnce({message: 'ok'})
        .mockRejectedValueOnce({response: {data: {detail: 'Too many codes.'}}});

      render(
        <MemoryRouter>
          <SubscribePage />
        </MemoryRouter>,
      );

      fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'test@example.com'}});
      fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);

      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByLabelText('Verification Code')).toBeInTheDocument();

      for (let i = 0; i < 30; i += 1) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(1000);
        });
      }

      fireEvent.click(screen.getByRole('button', {name: 'Resend code'}));

      await act(async () => {
        await Promise.resolve();
      });

      expect(screen.getByText('Too many codes.')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('returns to the email step from the code step', async () => {
    render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: 'test@example.com'}});
    fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);
    await screen.findByLabelText('Verification Code');

    fireEvent.click(screen.getByRole('button', {name: 'Use a different email or phone'}));

    expect(screen.getByLabelText('Email or Phone')).toBeInTheDocument();
  });

  it('advances to manage when auth completes while on the email step', async () => {
    mockUseAuth.mockReturnValue({...baseAuth});
    const {rerender} = render(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );
    expect(screen.getByLabelText('Email or Phone')).toBeInTheDocument();

    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    rerender(
      <MemoryRouter>
        <SubscribePage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText('Manage your email and text message subscription preferences below.'),
    ).toBeInTheDocument();
  });

  it('resends the phone code via the SMS resend path', async () => {
    vi.useFakeTimers();
    try {
      render(
        <MemoryRouter>
          <SubscribePage />
        </MemoryRouter>,
      );

      fireEvent.change(screen.getByLabelText('Email or Phone'), {target: {value: '(202) 555-0123'}});
      fireEvent.submit(screen.getByLabelText('Email or Phone').closest('form')!);

      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByLabelText('Verification Code')).toBeInTheDocument();

      for (let i = 0; i < 30; i += 1) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(1000);
        });
      }

      fireEvent.click(screen.getByRole('button', {name: 'Resend code'}));

      await act(async () => {
        await Promise.resolve();
      });

      expect(baseAuth.requestPhoneAuthCode).toHaveBeenCalledTimes(2);
      expect(baseAuth.requestPhoneAuthCode).toHaveBeenLastCalledWith('2025550123', '1-US', 'subscribe');
    } finally {
      vi.useRealTimers();
    }
  });
});
