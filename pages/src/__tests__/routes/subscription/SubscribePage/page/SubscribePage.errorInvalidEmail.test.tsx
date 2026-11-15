import {cleanup, fireEvent, render, screen} from '@testing-library/react';
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
});
