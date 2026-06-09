import {act, renderHook, waitFor} from '@testing-library/react';
import type {ChangeEvent, FormEvent} from 'react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

const navigateMock = vi.hoisted(() => vi.fn());
const authContextMock = vi.hoisted(() => ({
  value: {
    isAuthenticated: true,
    logout: vi.fn(),
    user: {email: 'member@example.com'},
    requiresProfileCompletion: false,
  },
}));

const authApiMock = vi.hoisted(() => ({
  confirmAccountDeletion: vi.fn(),
  confirmPasswordChange: vi.fn(),
  getProfile: vi.fn(),
  requestAccountDeletionCode: vi.fn(),
  requestPasswordChangeCode: vi.fn(),
  updateProfileFields: vi.fn(),
  uploadProfileImage: vi.fn(),
  verifyAccountDeletionCode: vi.fn(),
  verifyPasswordChangeCode: vi.fn(),
}));

const eventsApiMock = vi.hoisted(() => ({
  fetchMyTickets: vi.fn(),
  fetchRegistrationOptions: vi.fn(),
  resendTicketEmail: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('@/features/auth/components/AuthContext', () => ({
  useAuth: () => authContextMock.value,
}));

vi.mock('@/features/auth/api', async () => {
  const actual = await vi.importActual<typeof import('@/features/auth/api')>('@/features/auth/api');
  return {
    ...actual,
    confirmAccountDeletion: authApiMock.confirmAccountDeletion,
    confirmPasswordChange: authApiMock.confirmPasswordChange,
    getProfile: authApiMock.getProfile,
    requestAccountDeletionCode: authApiMock.requestAccountDeletionCode,
    requestPasswordChangeCode: authApiMock.requestPasswordChangeCode,
    updateProfileFields: authApiMock.updateProfileFields,
    uploadProfileImage: authApiMock.uploadProfileImage,
    verifyAccountDeletionCode: authApiMock.verifyAccountDeletionCode,
    verifyPasswordChangeCode: authApiMock.verifyPasswordChangeCode,
  };
});

vi.mock('@/features/events/api', async () => {
  const actual = await vi.importActual<typeof import('@/features/events/api')>('@/features/events/api');
  return {
    ...actual,
    fetchMyTickets: eventsApiMock.fetchMyTickets,
    fetchRegistrationOptions: eventsApiMock.fetchRegistrationOptions,
    resendTicketEmail: eventsApiMock.resendTicketEmail,
  };
});

import {useAccountDashboard} from '@/features/auth/components/pages/account/useAccountDashboard';

const profile = {
  email: 'member@example.com',
  primary_email_id: 'primary-email',
  first_name: 'Ada',
  middle_name: 'M',
  last_name: 'Lovelace',
  organization: 'UC Merced',
  title: 'Director',
  profile_image: '/media/profile.png',
  email_subscribe: true,
};

const flushLoads = async (result: ReturnType<typeof renderHook<typeof useAccountDashboard>>['result']) => {
  await waitFor(() => expect(result.current.profileLoading).toBe(false));
  await waitFor(() => expect(result.current.ticketsLoading).toBe(false));
  await waitFor(() => expect(result.current.liveEventLoading).toBe(false));
};

describe('useAccountDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authContextMock.value = {
      isAuthenticated: true,
      logout: vi.fn(),
      user: {email: 'member@example.com'},
      requiresProfileCompletion: false,
    };
    authApiMock.getProfile.mockResolvedValue(profile);
    authApiMock.updateProfileFields.mockResolvedValue({...profile, first_name: 'Grace'});
    authApiMock.uploadProfileImage.mockResolvedValue({...profile, profile_image: '/media/new.png'});
    authApiMock.requestPasswordChangeCode.mockResolvedValue({message: 'Password code sent.'});
    authApiMock.verifyPasswordChangeCode.mockResolvedValue({verification_token: 'password-token', message: 'Password code verified.'});
    authApiMock.confirmPasswordChange.mockResolvedValue({message: 'Password changed.'});
    authApiMock.requestAccountDeletionCode.mockResolvedValue({message: 'Delete code sent.'});
    authApiMock.verifyAccountDeletionCode.mockResolvedValue({verification_token: 'delete-token', message: 'Delete code verified.'});
    authApiMock.confirmAccountDeletion.mockResolvedValue({message: 'Deleted.'});
    eventsApiMock.fetchMyTickets.mockResolvedValue([{id: 'ticket-1'}]);
    eventsApiMock.fetchRegistrationOptions.mockResolvedValue({id: 'event-1'});
    eventsApiMock.resendTicketEmail.mockResolvedValue({message: 'resent'});
  });

  it('redirects when auth state cannot render the account dashboard', () => {
    authContextMock.value = {
      ...authContextMock.value,
      isAuthenticated: false,
    };

    const {result, rerender} = renderHook(() => useAccountDashboard());

    expect(result.current.canRender).toBe(false);
    expect(navigateMock).toHaveBeenCalledWith('/login', {replace: true});

    authContextMock.value = {
      ...authContextMock.value,
      isAuthenticated: true,
      requiresProfileCompletion: true,
    };
    rerender();

    expect(navigateMock).toHaveBeenCalledWith('/complete-profile', {replace: true});
  });

  it('loads profile, tickets, and live event data for authenticated members', async () => {
    const {result} = renderHook(() => useAccountDashboard());

    await flushLoads(result);

    expect(result.current.canRender).toBe(true);
    expect(result.current.profile).toEqual(profile);
    expect(result.current.firstName).toBe('Ada');
    expect(result.current.middleName).toBe('M');
    expect(result.current.lastName).toBe('Lovelace');
    expect(result.current.organizationType).toBe('organization');
    expect(result.current.organization).toBe('UC Merced');
    expect(result.current.title).toBe('Director');
    expect(result.current.profileImage).toBe('/media/profile.png');
    expect(result.current.tickets).toEqual([{id: 'ticket-1'}]);
    expect(result.current.liveEventOptions).toEqual({id: 'event-1'});
  });

  it('normalizes individual profile organizations and can cancel edits', async () => {
    authApiMock.getProfile.mockResolvedValueOnce({...profile, organization: ' personal ', title: 'Ignored'});

    const {result} = renderHook(() => useAccountDashboard());
    await flushLoads(result);

    expect(result.current.organizationType).toBe('individual');
    expect(result.current.organization).toBe('');

    act(() => {
      result.current.setFirstName('Changed');
      result.current.setOrganization('Changed Org');
      result.current.setTitle('Changed Title');
      result.current.setIsEditingProfile(true);
    });

    act(() => result.current.handleCancelEditing());

    expect(result.current.firstName).toBe('Ada');
    expect(result.current.organizationType).toBe('individual');
    expect(result.current.organization).toBe('');
    expect(result.current.title).toBe('Ignored');
  });

  it('updates profile fields and handles profile load failures', async () => {
    const {result} = renderHook(() => useAccountDashboard());
    await flushLoads(result);

    act(() => {
      result.current.setFirstName(' Grace ');
      result.current.setMiddleName(' B ');
      result.current.setLastName(' Hopper ');
      result.current.setOrganization(' Navy ');
      result.current.setTitle(' Rear Admiral ');
      result.current.setIsEditingProfile(true);
    });

    await act(async () => {
      await result.current.handleProfileSubmit({preventDefault: vi.fn()} as unknown as FormEvent);
    });

    expect(authApiMock.updateProfileFields).toHaveBeenCalledWith({
      first_name: 'Grace',
      middle_name: 'B',
      last_name: 'Hopper',
      organization: 'Navy',
      title: 'Rear Admiral',
    });
    expect(result.current.profileMessage).toBe('Profile updated successfully.');
    expect(result.current.isEditingProfile).toBe(false);

    authApiMock.getProfile.mockRejectedValueOnce({response: {data: {detail: 'No profile'}}});
    await act(async () => {
      await result.current.loadProfile();
    });
    expect(result.current.profileError).toBe('No profile');
  });

  it('validates and uploads profile images', async () => {
    const {result} = renderHook(() => useAccountDashboard());
    await flushLoads(result);

    await act(async () => {
      await result.current.handleImageChange({target: {files: []}} as unknown as ChangeEvent<HTMLInputElement>);
    });
    expect(authApiMock.uploadProfileImage).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.handleImageChange({
        target: {files: [new File(['text'], 'note.txt', {type: 'text/plain'})]},
      } as unknown as ChangeEvent<HTMLInputElement>);
    });
    expect(result.current.imageError).toBe('Please select an image file.');

    await act(async () => {
      await result.current.handleImageChange({
        target: {files: [new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'large.png', {type: 'image/png'})]},
      } as unknown as ChangeEvent<HTMLInputElement>);
    });
    expect(result.current.imageError).toBe('Image size should be less than 5MB.');

    const target = {
      files: [new File(['image'], 'avatar.png', {type: 'image/png'})],
      value: 'avatar.png',
    };
    await act(async () => {
      await result.current.handleImageChange({target} as unknown as ChangeEvent<HTMLInputElement>);
    });

    expect(authApiMock.uploadProfileImage).toHaveBeenCalledWith(target.files[0]);
    expect(result.current.profileImage).toBe('/media/new.png');
    expect(result.current.profileMessage).toBe('Profile image updated successfully.');
    expect(target.value).toBe('');
  });

  it('runs password change verification and confirmation flows', async () => {
    const {result} = renderHook(() => useAccountDashboard());
    await flushLoads(result);

    await act(async () => {
      await result.current.handlePasswordRequestCode();
    });
    expect(authApiMock.requestPasswordChangeCode).toHaveBeenCalledWith('member@example.com');
    expect(result.current.passwordCodeRequested).toBe(true);

    act(() => result.current.setPasswordCode('123456'));
    await act(async () => {
      await result.current.handlePasswordVerifyCode({preventDefault: vi.fn()} as unknown as FormEvent);
    });
    expect(result.current.passwordVerificationToken).toBe('password-token');

    act(() => {
      result.current.setNewPassword('new-password');
      result.current.setConfirmPassword('different');
    });
    await act(async () => {
      await result.current.handlePasswordConfirm({preventDefault: vi.fn()} as unknown as FormEvent);
    });
    expect(result.current.passwordError).toBe('Passwords do not match.');

    act(() => {
      result.current.setConfirmPassword('new-password');
    });
    await act(async () => {
      await result.current.handlePasswordConfirm({preventDefault: vi.fn()} as unknown as FormEvent);
    });

    expect(authApiMock.confirmPasswordChange).toHaveBeenCalledWith('password-token', 'new-password', 'new-password');
    expect(result.current.passwordMessage).toBe('Password changed.');
    expect(result.current.passwordVerificationToken).toBeNull();
  });

  it('handles missing password email before requesting a code', async () => {
    authContextMock.value = {
      ...authContextMock.value,
      user: {email: ''},
    };
    authApiMock.getProfile.mockResolvedValueOnce({...profile, email: ''});
    const {result} = renderHook(() => useAccountDashboard());
    await flushLoads(result);

    await act(async () => {
      await result.current.handlePasswordRequestCode();
    });

    expect(result.current.passwordError).toBe('No account email is available for password verification.');
  });

  it('runs account deletion and ticket resend flows', async () => {
    const {result} = renderHook(() => useAccountDashboard());
    await flushLoads(result);

    await act(async () => {
      await result.current.handleResendTicketEmail('ticket-1');
    });
    expect(eventsApiMock.resendTicketEmail).toHaveBeenCalledWith('ticket-1');
    expect(eventsApiMock.fetchMyTickets).toHaveBeenCalledTimes(2);

    await act(async () => {
      await result.current.handleDeleteRequestCode();
    });
    expect(result.current.deleteCodeRequested).toBe(true);

    act(() => result.current.setDeleteCode('654321'));
    await act(async () => {
      await result.current.handleDeleteVerifyCode({preventDefault: vi.fn()} as unknown as FormEvent);
    });
    expect(result.current.deleteVerificationToken).toBe('delete-token');

    await act(async () => {
      await result.current.handleDeleteConfirm({preventDefault: vi.fn()} as unknown as FormEvent);
    });

    expect(authApiMock.confirmAccountDeletion).toHaveBeenCalledWith('delete-token');
    expect(authContextMock.value.logout).toHaveBeenCalled();
    expect(navigateMock).toHaveBeenCalledWith('/login', {replace: true});
  });
});
