import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import type {FormEvent} from 'react';

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

const formEvent = () => ({preventDefault: vi.fn()}) as unknown as FormEvent;

describe('useAccountDashboard — password change and account deletion', () => {
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

  it('falls back to the default password confirm message', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    mocks.authApi.requestPasswordChangeCode.mockResolvedValue({message: 'sent'});
    await act(async () => {
      await result.current.handlePasswordRequestCode();
    });
    act(() => result.current.setPasswordCode('123456'));
    mocks.authApi.verifyPasswordChangeCode.mockResolvedValue({verification_token: 'tok', message: 'verified'});
    await act(async () => {
      await result.current.handlePasswordVerifyCode(formEvent());
    });

    act(() => {
      result.current.setNewPassword('newpass');
      result.current.setConfirmPassword('newpass');
    });
    mocks.authApi.confirmPasswordChange.mockResolvedValue({});
    await act(async () => {
      await result.current.handlePasswordConfirm(formEvent());
    });

    expect(result.current.passwordMessage).toBe('Password changed successfully.');
  });

  it('falls back to the default deletion verify message', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    act(() => result.current.setDeleteCode('123456'));
    mocks.authApi.verifyAccountDeletionCode.mockResolvedValue({verification_token: 'tok'});
    await act(async () => {
      await result.current.handleDeleteVerifyCode(formEvent());
    });

    expect(result.current.deleteMessage).toBe('Deletion code verified.');
  });

  it('falls back to the default deletion confirm message', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    mocks.authApi.requestAccountDeletionCode.mockResolvedValue({message: 'sent'});
    await act(async () => {
      await result.current.handleDeleteRequestCode();
    });
    act(() => result.current.setDeleteCode('123456'));
    mocks.authApi.verifyAccountDeletionCode.mockResolvedValue({verification_token: 'tok', message: 'verified'});
    await act(async () => {
      await result.current.handleDeleteVerifyCode(formEvent());
    });

    mocks.authApi.confirmAccountDeletion.mockResolvedValue({});
    await act(async () => {
      await result.current.handleDeleteConfirm(formEvent());
    });

    expect(result.current.deleteMessage).toBe('Account deleted successfully.');
  });
});
