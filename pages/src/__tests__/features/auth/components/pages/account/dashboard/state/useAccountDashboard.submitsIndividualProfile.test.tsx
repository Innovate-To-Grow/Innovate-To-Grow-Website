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

  it('submits an individual profile with the literal Individual organization', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    mocks.authApi.updateProfileFields.mockResolvedValue(baseProfile({organization: 'Individual'}));
    act(() => result.current.setOrganizationType('individual'));
    await act(async () => {
      await result.current.handleProfileSubmit(formEvent());
    });

    expect(mocks.authApi.updateProfileFields).toHaveBeenCalledWith({
      first_name: 'Ada',
      middle_name: '',
      last_name: 'Lovelace',
      organization: 'Individual',
      title: '',
    });
    expect(result.current.profileMessage).toBe('Profile updated successfully.');
    expect(result.current.isEditingProfile).toBe(false);
  });

  it('submits an organization profile with trimmed fields', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    mocks.authApi.updateProfileFields.mockResolvedValue(baseProfile());
    act(() => {
      result.current.setOrganization('  Acme Corp  ');
      result.current.setTitle('  CEO  ');
    });
    await act(async () => {
      await result.current.handleProfileSubmit(formEvent());
    });

    expect(mocks.authApi.updateProfileFields).toHaveBeenCalledWith({
      first_name: 'Ada',
      middle_name: '',
      last_name: 'Lovelace',
      organization: 'Acme Corp',
      title: 'CEO',
    });
  });

  it('surfaces a profile save failure', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    mocks.authApi.updateProfileFields.mockRejectedValue({response: {data: {detail: 'Save failed'}}});
    await act(async () => {
      await result.current.handleProfileSubmit(formEvent());
    });

    expect(result.current.profileError).toBe('Save failed');
    expect(result.current.profileSaving).toBe(false);
  });

  it('cancel editing resets fields from the loaded profile', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    act(() => {
      result.current.setIsEditingProfile(true);
      result.current.setFirstName('Changed');
      result.current.setLastName('Name');
      result.current.setOrganization('Other');
      result.current.setOrganizationType('individual');
      result.current.setTitle('T');
    });
    act(() => result.current.handleCancelEditing());

    expect(result.current.isEditingProfile).toBe(false);
    expect(result.current.firstName).toBe('Ada');
    expect(result.current.lastName).toBe('Lovelace');
    expect(result.current.organizationType).toBe('organization');
    expect(result.current.organization).toBe('Acme Corp');
    expect(result.current.title).toBe('CEO');
  });

  it('cancel editing with no loaded profile resets to empty', async () => {
    mocks.authApi.getProfile.mockRejectedValue({response: {data: {detail: 'nope'}}});
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    act(() => {
      result.current.setFirstName('Changed');
      result.current.setOrganization('Other');
      result.current.setOrganizationType('individual');
    });
    act(() => result.current.handleCancelEditing());

    expect(result.current.firstName).toBe('');
    expect(result.current.organizationType).toBe('organization');
    expect(result.current.organization).toBe('');
  });

  it('cancel editing restores an individual organization type', async () => {
    mocks.authApi.getProfile.mockResolvedValue(baseProfile({organization: 'Individual'}));
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    act(() => {
      result.current.setIsEditingProfile(true);
      result.current.setOrganizationType('organization');
      result.current.setOrganization('Acme');
    });
    act(() => result.current.handleCancelEditing());

    expect(result.current.organizationType).toBe('individual');
    expect(result.current.organization).toBe('');
  });
});
