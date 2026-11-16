import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import type {ChangeEvent} from 'react';
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

  it('loads tickets and registration events into state', async () => {
    const ticket = {
      id: 'registration-1',
      event: {id: 'event-1', name: 'Spring', slug: 'spring', date: '2026-05-01', location: 'Campus', description: ''},
    } as unknown as import('@/features/events/api').Registration;
    const event = {id: 'event-2', name: 'Fall', slug: 'fall', date: '2026-10-01', location: 'Hall', description: '', registration: null};
    mocks.eventsApi.fetchMyTickets.mockResolvedValue([ticket]);
    mocks.eventsApi.fetchRegistrationEvents.mockResolvedValue([event]);

    const {result} = renderHook(() => useAccountDashboard(), {wrapper});

    await waitFor(() => expect(result.current.ticketsLoading).toBe(false));
    await waitFor(() => expect(result.current.registrationEventsLoading).toBe(false));
    expect(result.current.tickets).toEqual([ticket]);
    expect(result.current.registrationEvents).toEqual([event]);
  });

  it('keeps empty tickets when the tickets fetch fails', async () => {
    mocks.eventsApi.fetchMyTickets.mockRejectedValue(new Error('boom'));

    const {result} = renderHook(() => useAccountDashboard(), {wrapper});

    await waitFor(() => expect(result.current.ticketsLoading).toBe(false));
    expect(result.current.tickets).toEqual([]);
  });

  it('clears registration events when the events fetch fails', async () => {
    mocks.eventsApi.fetchRegistrationEvents.mockRejectedValue(new Error('boom'));

    const {result} = renderHook(() => useAccountDashboard(), {wrapper});

    await waitFor(() => expect(result.current.registrationEventsLoading).toBe(false));
    expect(result.current.registrationEvents).toEqual([]);
  });

  it('ignores an empty image selection', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    const event = {target: {files: [], value: ''}} as unknown as ChangeEvent<HTMLInputElement>;
    await act(async () => {
      await result.current.handleImageChange(event);
    });

    expect(mocks.authApi.uploadProfileImage).not.toHaveBeenCalled();
    expect(result.current.imageError).toBeNull();
  });

  it('rejects a non-image file', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    const file = new File(['x'], 'x.txt', {type: 'text/plain'});
    const event = {target: {files: [file], value: 'x'}} as unknown as ChangeEvent<HTMLInputElement>;
    await act(async () => {
      await result.current.handleImageChange(event);
    });

    expect(result.current.imageError).toBe('Please select an image file.');
  });

  it('rejects an image larger than 5MB', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    const file = new File([new ArrayBuffer(5 * 1024 * 1024 + 1)], 'big.png', {type: 'image/png'});
    const event = {target: {files: [file], value: 'x'}} as unknown as ChangeEvent<HTMLInputElement>;
    await act(async () => {
      await result.current.handleImageChange(event);
    });

    expect(result.current.imageError).toBe('Image size should be less than 5MB.');
  });

  it('uploads a valid image and applies the updated profile', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    const file = new File(['a'], 'a.png', {type: 'image/png'});
    mocks.authApi.uploadProfileImage.mockResolvedValue(baseProfile({profile_image: '/media/new.png'}));
    const event = {target: {files: [file], value: 'fake'}} as unknown as ChangeEvent<HTMLInputElement>;
    await act(async () => {
      await result.current.handleImageChange(event);
    });

    expect(mocks.authApi.uploadProfileImage).toHaveBeenCalledWith(file);
    expect(result.current.profileImage).toBe('/media/new.png');
    expect(result.current.profileMessage).toBe('Profile image updated successfully.');
    expect(result.current.imageUploading).toBe(false);
    expect(result.current.imageError).toBeNull();
    expect((event.target as HTMLInputElement).value).toBe('');
  });

  it('surfaces an image upload failure', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    const file = new File(['a'], 'a.png', {type: 'image/png'});
    mocks.authApi.uploadProfileImage.mockRejectedValue({response: {data: {detail: 'Upload failed'}}});
    const event = {target: {files: [file], value: 'fake'}} as unknown as ChangeEvent<HTMLInputElement>;
    await act(async () => {
      await result.current.handleImageChange(event);
    });

    expect(result.current.imageError).toBe('Upload failed');
    expect(result.current.imageUploading).toBe(false);
  });
});
