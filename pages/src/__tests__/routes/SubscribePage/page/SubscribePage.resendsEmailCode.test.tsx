import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {SubscribePage} from '@/routes/SubscribePage/SubscribePage';
import {emailSignIn, phoneSignIn, profileData} from '@/__tests__/routes/SubscribePage/fixtures/subscribePageFixtures';

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
});
