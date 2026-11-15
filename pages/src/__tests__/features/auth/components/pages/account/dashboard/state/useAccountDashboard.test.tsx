import {cleanup, renderHook, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
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

  it('redirects to /login when unauthenticated', async () => {
    mocks.useAuth.mockReturnValue({
      isAuthenticated: false,
      isInitializing: false,
      requiresProfileCompletion: false,
      user: null,
      logout: mocks.logout,
    });

    const {result} = renderHook(() => useAccountDashboard(), {wrapper});

    expect(result.current.canRender).toBe(false);
    await waitFor(() => expect(screen.getByText('login-route')).toBeInTheDocument());
    expect(mocks.authApi.getProfile).not.toHaveBeenCalled();
  });

  it('redirects to /complete-profile when profile completion is required', async () => {
    mocks.useAuth.mockReturnValue({
      isAuthenticated: true,
      isInitializing: false,
      requiresProfileCompletion: true,
      user: {member_uuid: 'm-1', email: 'member@example.com'},
      logout: mocks.logout,
    });

    const {result} = renderHook(() => useAccountDashboard(), {wrapper});

    expect(result.current.canRender).toBe(false);
    await waitFor(() => expect(screen.getByText('complete-profile-route')).toBeInTheDocument());
    expect(mocks.authApi.getProfile).not.toHaveBeenCalled();
  });

  it('does not redirect while the session is still initializing', async () => {
    mocks.useAuth.mockReturnValue({
      isAuthenticated: true,
      isInitializing: true,
      requiresProfileCompletion: false,
      user: null,
      logout: mocks.logout,
    });

    const {result} = renderHook(() => useAccountDashboard(), {wrapper});

    expect(result.current.canRender).toBe(false);
    await waitFor(() => expect(mocks.authApi.getProfile).toHaveBeenCalled());
    expect(screen.queryByText('login-route')).not.toBeInTheDocument();
    expect(screen.queryByText('complete-profile-route')).not.toBeInTheDocument();
  });

  it('loads the profile and applies its fields', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});

    // Before the profile resolves, the display email falls back to the member email.
    expect(result.current.displayEmail).toBe('member@example.com');

    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    expect(result.current.profile).toEqual(baseProfile());
    expect(result.current.firstName).toBe('Ada');
    expect(result.current.middleName).toBe('');
    expect(result.current.lastName).toBe('Lovelace');
    expect(result.current.organization).toBe('Acme Corp');
    expect(result.current.title).toBe('CEO');
    expect(result.current.organizationType).toBe('organization');
    expect(result.current.displayEmail).toBe('ada@example.com');
    expect(result.current.canRender).toBe(true);
    expect(result.current.ticketsLoading).toBe(false);
    expect(result.current.registrationEventsLoading).toBe(false);
  });

  it('normalizes an individual organization and its profile image', async () => {
    mocks.authApi.getProfile.mockResolvedValue(
      baseProfile({email: '', organization: 'Individual', profile_image: '/media/a.png'}),
    );

    const {result} = renderHook(() => useAccountDashboard(), {wrapper});

    await waitFor(() => expect(result.current.profileLoading).toBe(false));
    expect(result.current.organizationType).toBe('individual');
    expect(result.current.organization).toBe('');
    expect(result.current.profileImage).toBe('/media/a.png');
    expect(result.current.displayEmail).toBe('member@example.com');
  });

  it('treats a "personal" organization as individual', async () => {
    mocks.authApi.getProfile.mockResolvedValue(baseProfile({organization: 'personal'}));

    const {result} = renderHook(() => useAccountDashboard(), {wrapper});

    await waitFor(() => expect(result.current.profileLoading).toBe(false));
    expect(result.current.organizationType).toBe('individual');
    expect(result.current.organization).toBe('');
  });

  it('records a profile load failure as profileError', async () => {
    mocks.authApi.getProfile.mockRejectedValue({response: {data: {detail: 'Profile unavailable'}}});

    const {result} = renderHook(() => useAccountDashboard(), {wrapper});

    await waitFor(() => expect(result.current.profileLoading).toBe(false));
    expect(result.current.profileError).toBe('Profile unavailable');
  });
});
