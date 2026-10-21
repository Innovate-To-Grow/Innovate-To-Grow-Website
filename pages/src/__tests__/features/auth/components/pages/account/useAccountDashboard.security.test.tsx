import {act, cleanup, renderHook, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import type {FormEvent, ReactNode} from 'react';

import type {ProfileResponse} from '@/features/auth/api';
import {useAccountDashboard} from '@/features/auth/components/pages/account/useAccountDashboard';

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

const baseProfile = (overrides: Partial<ProfileResponse> = {}): ProfileResponse => ({
  member_uuid: 'm-1',
  email: 'ada@example.com',
  email_verified: true,
  primary_email_id: 'pe-1',
  first_name: 'Ada',
  middle_name: '',
  last_name: 'Lovelace',
  organization: 'Acme Corp',
  title: 'CEO',
  email_subscribe: true,
  is_staff: false,
  is_active: true,
  date_joined: '2026-01-01T00:00:00Z',
  ...overrides,
});

const wrapper = ({children}: {children: ReactNode}) => (
  <MemoryRouter initialEntries={['/account']}>
    <Routes>
      <Route path="/account" element={<>{children}</>} />
      <Route path="/login" element={<div>login-route</div>} />
      <Route path="/complete-profile" element={<div>complete-profile-route</div>} />
    </Routes>
  </MemoryRouter>
);

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

  it('requests a password change code and reports the returned message', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    mocks.authApi.requestPasswordChangeCode.mockResolvedValue({channel: 'email', message: 'Code sent.'});
    await act(async () => {
      await result.current.handlePasswordRequestCode();
    });

    expect(mocks.authApi.requestPasswordChangeCode).toHaveBeenCalledWith('ada@example.com');
    expect(result.current.passwordCodeRequested).toBe(true);
    expect(result.current.passwordChannel).toBe('email');
    expect(result.current.passwordMessage).toBe('Code sent.');
  });

  it('builds a default SMS password message when none is returned', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    mocks.authApi.requestPasswordChangeCode.mockResolvedValue({channel: 'sms', destination: '(•••) •••-4567'});
    await act(async () => {
      await result.current.handlePasswordRequestCode();
    });

    expect(result.current.passwordChannel).toBe('sms');
    expect(result.current.passwordMessage).toBe('We texted a code to (•••) •••-4567.');
  });

  it('requests a password code without an email for phone-only accounts', async () => {
    mocks.useAuth.mockReturnValue({
      isAuthenticated: true,
      isInitializing: false,
      requiresProfileCompletion: false,
      user: {member_uuid: 'm-1', email: ''},
      logout: mocks.logout,
    });
    mocks.authApi.getProfile.mockResolvedValue(baseProfile({email: ''}));
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    mocks.authApi.requestPasswordChangeCode.mockResolvedValue({message: 'Sent'});
    await act(async () => {
      await result.current.handlePasswordRequestCode();
    });

    expect(mocks.authApi.requestPasswordChangeCode).toHaveBeenCalledWith(undefined);
  });

  it('surfaces a password code request failure', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    mocks.authApi.requestPasswordChangeCode.mockRejectedValue({response: {data: {detail: 'Request failed'}}});
    await act(async () => {
      await result.current.handlePasswordRequestCode();
    });

    expect(result.current.passwordError).toBe('Request failed');
    expect(result.current.passwordCodeRequested).toBe(false);
  });

  it('verifies the password code and stores the verification token', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    act(() => result.current.setPasswordCode('123456'));
    mocks.authApi.verifyPasswordChangeCode.mockResolvedValue({message: 'Verified', verification_token: 'tok'});
    await act(async () => {
      await result.current.handlePasswordVerifyCode(formEvent());
    });

    expect(mocks.authApi.verifyPasswordChangeCode).toHaveBeenCalledWith('123456', 'ada@example.com');
    expect(result.current.passwordVerificationToken).toBe('tok');
    expect(result.current.passwordMessage).toBe('Verified');
  });

  it('falls back to the default password verify message', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    act(() => result.current.setPasswordCode('123456'));
    mocks.authApi.verifyPasswordChangeCode.mockResolvedValue({verification_token: 'tok'});
    await act(async () => {
      await result.current.handlePasswordVerifyCode(formEvent());
    });

    expect(result.current.passwordMessage).toBe('Code verified. You can now enter a new password.');
  });

  it('surfaces a password code verify failure', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    act(() => result.current.setPasswordCode('123456'));
    mocks.authApi.verifyPasswordChangeCode.mockRejectedValue({response: {data: {detail: 'Bad code'}}});
    await act(async () => {
      await result.current.handlePasswordVerifyCode(formEvent());
    });

    expect(result.current.passwordError).toBe('Bad code');
  });

  it('blocks password confirm without a verification token', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    await act(async () => {
      await result.current.handlePasswordConfirm(formEvent());
    });

    expect(result.current.passwordError).toBe('Verify your code before changing your password.');
    expect(mocks.authApi.confirmPasswordChange).not.toHaveBeenCalled();
  });

  it('blocks password confirm when passwords do not match', async () => {
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
      result.current.setNewPassword('one');
      result.current.setConfirmPassword('two');
    });
    await act(async () => {
      await result.current.handlePasswordConfirm(formEvent());
    });

    expect(result.current.passwordError).toBe('Passwords do not match.');
  });

  it('confirms the password change and resets the form', async () => {
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
    mocks.authApi.confirmPasswordChange.mockResolvedValue({message: 'Password changed successfully.'});
    await act(async () => {
      await result.current.handlePasswordConfirm(formEvent());
    });

    expect(mocks.authApi.confirmPasswordChange).toHaveBeenCalledWith('tok', 'newpass', 'newpass');
    expect(result.current.passwordMessage).toBe('Password changed successfully.');
    expect(result.current.passwordCodeRequested).toBe(false);
    expect(result.current.passwordVerificationToken).toBeNull();
  });

  it('surfaces a password confirm failure', async () => {
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
    mocks.authApi.confirmPasswordChange.mockRejectedValue({response: {data: {detail: 'Weak password'}}});
    await act(async () => {
      await result.current.handlePasswordConfirm(formEvent());
    });

    expect(result.current.passwordError).toBe('Weak password');
  });

  it('requests a deletion code', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    mocks.authApi.requestAccountDeletionCode.mockResolvedValue({message: 'Deletion verification code sent.'});
    await act(async () => {
      await result.current.handleDeleteRequestCode();
    });

    expect(result.current.deleteCodeRequested).toBe(true);
    expect(result.current.deleteMessage).toBe('Deletion verification code sent.');
  });

  it('falls back to the default deletion request message', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    mocks.authApi.requestAccountDeletionCode.mockResolvedValue({});
    await act(async () => {
      await result.current.handleDeleteRequestCode();
    });

    expect(result.current.deleteMessage).toBe('Deletion verification code sent.');
  });

  it('surfaces a deletion code request failure', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    mocks.authApi.requestAccountDeletionCode.mockRejectedValue({response: {data: {detail: 'Request failed'}}});
    await act(async () => {
      await result.current.handleDeleteRequestCode();
    });

    expect(result.current.deleteError).toBe('Request failed');
    expect(result.current.deleteCodeRequested).toBe(false);
  });

  it('verifies the deletion code and stores the verification token', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    act(() => result.current.setDeleteCode('123456'));
    mocks.authApi.verifyAccountDeletionCode.mockResolvedValue({verification_token: 'tok', message: 'Deletion code verified.'});
    await act(async () => {
      await result.current.handleDeleteVerifyCode(formEvent());
    });

    expect(mocks.authApi.verifyAccountDeletionCode).toHaveBeenCalledWith('123456');
    expect(result.current.deleteVerificationToken).toBe('tok');
    expect(result.current.deleteMessage).toBe('Deletion code verified.');
  });

  it('surfaces a deletion code verify failure', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    act(() => result.current.setDeleteCode('123456'));
    mocks.authApi.verifyAccountDeletionCode.mockRejectedValue({response: {data: {detail: 'Bad code'}}});
    await act(async () => {
      await result.current.handleDeleteVerifyCode(formEvent());
    });

    expect(result.current.deleteError).toBe('Bad code');
  });

  it('blocks deletion without a verification token', async () => {
    const {result} = renderHook(() => useAccountDashboard(), {wrapper});
    await waitFor(() => expect(result.current.profileLoading).toBe(false));

    await act(async () => {
      await result.current.handleDeleteConfirm(formEvent());
    });

    expect(result.current.deleteError).toBe('Verify your deletion code before deleting your account.');
    expect(mocks.authApi.confirmAccountDeletion).not.toHaveBeenCalled();
  });

  it('confirms deletion, logs out, and navigates to login', async () => {
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

    mocks.authApi.confirmAccountDeletion.mockResolvedValue({message: 'Account deleted successfully.'});
    await act(async () => {
      await result.current.handleDeleteConfirm(formEvent());
    });

    expect(mocks.authApi.confirmAccountDeletion).toHaveBeenCalledWith('tok');
    expect(mocks.logout).toHaveBeenCalled();
    expect(result.current.deleteMessage).toBe('Account deleted successfully.');
    await waitFor(() => expect(screen.getByText('login-route')).toBeInTheDocument());
  });

  it('surfaces a deletion confirm failure', async () => {
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

    mocks.authApi.confirmAccountDeletion.mockRejectedValue({response: {data: {detail: 'Deletion failed'}}});
    await act(async () => {
      await result.current.handleDeleteConfirm(formEvent());
    });

    expect(result.current.deleteError).toBe('Deletion failed');
  });

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
