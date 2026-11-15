import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
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

describe('SubscribePage — the profile step', () => {
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

  it('tolerates null profile fields and treats Personal as an individual', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    mockGetProfile.mockResolvedValue({
      ...profileData,
      first_name: null,
      middle_name: null,
      last_name: null,
      organization: 'Personal',
      title: null,
    });

    render(
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
        <SubscribePage />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mockGetProfile).toHaveBeenCalled());
    expect(await screen.findByLabelText(/first name/i)).toHaveValue('');
    expect(screen.getByLabelText(/last name/i)).toHaveValue('');
    expect(screen.queryByPlaceholderText('Company or organization name')).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Your title or position (e.g. CEO, Director)')).not.toBeInTheDocument();
  });

  it('ignores a stale profile response after unmounting', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    let resolveProfile!: (value: typeof profileData) => void;
    mockGetProfile.mockReturnValue(
      new Promise((resolve) => {
        resolveProfile = resolve;
      }),
    );

    const {unmount} = render(
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
        <SubscribePage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(mockGetProfile).toHaveBeenCalled());

    unmount();
    await act(async () => {
      resolveProfile(profileData);
      await Promise.resolve();
    });

    expect(mockGetProfile).toHaveBeenCalledTimes(1);
  });

  it('ignores a stale profile error after unmounting', async () => {
    mockUseAuth.mockReturnValue({
      ...baseAuth,
      user: {member_uuid: 'uuid-1', email: 'member@example.com'},
      isAuthenticated: true,
    });
    let rejectProfile!: (reason: unknown) => void;
    mockGetProfile.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectProfile = reject;
      }),
    );

    const {unmount} = render(
      <MemoryRouter initialEntries={['/subscribe?step=profile']}>
        <SubscribePage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(mockGetProfile).toHaveBeenCalled());

    unmount();
    await act(async () => {
      rejectProfile(new Error('down'));
      await Promise.resolve();
    });

    expect(mockGetProfile).toHaveBeenCalledTimes(1);
  });
});
