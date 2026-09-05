import {act, cleanup, renderHook, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import type {ChangeEvent, FormEvent, ReactNode} from 'react';

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
