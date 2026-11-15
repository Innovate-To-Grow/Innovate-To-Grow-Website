import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import type {ProfileResponse} from '@/features/auth/api';
import {useAccountDashboard} from '@/features/auth/components/pages/account/dashboard/useAccountDashboard';
import {baseProfile, wrapper} from '@/__tests__/features/auth/components/pages/account/dashboard/fixtures/useAccountDashboardFixtures';

const mocks = vi.hoisted(() => ({
  useAuth: vi.fn(),
  logout: vi.fn(),
  authApi: {
    confirmAccountDeletion: vi.fn(),
    confirmPasswordChange: vi.fn(),
    getProfile: vi.fn(),
    requestAccountDeletionCode: vi.fn(),
    requestPasswordChangeCode: vi.fn(),
    updateProfileFields: vi.fn(),
    uploadProfileImage: vi.fn(),
    verifyAccountDeletionCode: vi.fn(),
    verifyPasswordChangeCode: vi.fn(),
  },
  eventsApi: {
    fetchRegistrationEvents: vi.fn(),
    fetchMyTickets: vi.fn(),
    resendTicketEmail: vi.fn(),
  },
}));

vi.mock('@/features/auth/components/AuthContext', () => ({
  useAuth: () => mocks.useAuth(),
}));

vi.mock('@/features/auth/api', async () => {
  const actual = await vi.importActual<typeof import('@/features/auth/api')>('@/features/auth/api');
  return {
    ...actual,
    confirmAccountDeletion: (...args: unknown[]) => mocks.authApi.confirmAccountDeletion(...args),
    confirmPasswordChange: (...args: unknown[]) => mocks.authApi.confirmPasswordChange(...args),
    getProfile: () => mocks.authApi.getProfile(),
    requestAccountDeletionCode: () => mocks.authApi.requestAccountDeletionCode(),
    requestPasswordChangeCode: (...args: unknown[]) => mocks.authApi.requestPasswordChangeCode(...args),
    updateProfileFields: (...args: unknown[]) => mocks.authApi.updateProfileFields(...args),
    uploadProfileImage: (...args: unknown[]) => mocks.authApi.uploadProfileImage(...args),
    verifyAccountDeletionCode: (...args: unknown[]) => mocks.authApi.verifyAccountDeletionCode(...args),
    verifyPasswordChangeCode: (...args: unknown[]) => mocks.authApi.verifyPasswordChangeCode(...args),
  };
});

vi.mock('@/features/events/api', async () => {
  const actual = await vi.importActual<typeof import('@/features/events/api')>('@/features/events/api');
  return {
    ...actual,
    fetchRegistrationEvents: () => mocks.eventsApi.fetchRegistrationEvents(),
    fetchMyTickets: () => mocks.eventsApi.fetchMyTickets(),
    resendTicketEmail: (id: string) => mocks.eventsApi.resendTicketEmail(id),
  };
});

describe('useAccountDashboard', () => {
  beforeEach(() => {
    mocks.useAuth.mockReset();
    mocks.logout.mockReset();
    Object.values(mocks.authApi).forEach((fn) => fn.mockReset());
    Object.values(mocks.eventsApi).forEach((fn) => fn.mockReset());

    mocks.useAuth.mockReturnValue({
      isAuthenticated: true,
      isInitializing: false,
      requiresProfileCompletion: false,
      user: {member_uuid: 'm-1', email: 'member@example.com'},
      logout: mocks.logout,
    });
    mocks.authApi.getProfile.mockResolvedValue(baseProfile());
    mocks.eventsApi.fetchMyTickets.mockResolvedValue([]);
    mocks.eventsApi.fetchRegistrationEvents.mockResolvedValue([]);
  });

  afterEach(cleanup);

  it('resends a ticket email and refreshes tickets', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.ticketsLoading).toBe(false));

    mocks.eventsApi.resendTicketEmail.mockResolvedValue({message: 'sent'});
    await act(async () => {
      await result.current.handleResendTicketEmail('reg-1');
    });

    expect(mocks.eventsApi.resendTicketEmail).toHaveBeenCalledWith('reg-1');
    expect(mocks.eventsApi.fetchMyTickets).toHaveBeenCalledTimes(2);
    expect(result.current.resendingId).toBeNull();
  });

  it('clears the resending id when resend fails', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.ticketsLoading).toBe(false));

    mocks.eventsApi.resendTicketEmail.mockRejectedValue(new Error('fail'));
    await act(async () => {
      await expect(result.current.handleResendTicketEmail('reg-1')).rejects.toThrow('fail');
    });

    expect(result.current.resendingId).toBeNull();
  });

  it('retries a failed profile load', async () => {
    mocks.authApi.getProfile
      .mockRejectedValueOnce({response: {data: {detail: 'fail'}}})
      .mockResolvedValueOnce(baseProfile());

    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));
    expect(result.current.profileError).toBe('fail');

    await act(async () => {
      await result.current.loadProfile();
    });

    expect(result.current.profileError).toBeNull();
    expect(result.current.profile).toEqual(baseProfile());
    expect(result.current.profileLoading).toBe(false);
  });

  it('surfaces a failure when the profile retry itself fails', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    mocks.authApi.getProfile.mockRejectedValue({response: {data: {detail: 'Still down'}}});
    await act(async () => {
      await result.current.loadProfile();
    });

    expect(result.current.profileError).toBe('Still down');
    expect(result.current.profileLoading).toBe(false);
  });

  it('treats missing profile fields as empty strings', async () => {
    mocks.authApi.getProfile.mockResolvedValue({
      ...baseProfile(),
      first_name: null,
      middle_name: null,
      last_name: null,
      organization: null,
      title: null,
    } as unknown as ProfileResponse);

    const {result} = renderHook(() => useAccountDashboard(), {wrapper});

    await waitFor(() => expect(result.current.profileLoading).toBe(false));
    expect(result.current.firstName).toBe('');
    expect(result.current.middleName).toBe('');
    expect(result.current.lastName).toBe('');
    expect(result.current.organization).toBe('');
    expect(result.current.title).toBe('');
    expect(result.current.organizationType).toBe('organization');
  });
});
