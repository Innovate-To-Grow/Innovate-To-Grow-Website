import {useCallback, useEffect, useState, type ChangeEvent, type FormEvent} from 'react';
import {useNavigate} from 'react-router-dom';
import {useAuth} from '../../AuthContext';
import {
  confirmAccountDeletion,
  confirmPasswordChange,
  getProfile,
  requestAccountDeletionCode,
  requestPasswordChangeCode,
  updateProfileFields,
  uploadProfileImage,
  verifyAccountDeletionCode,
  verifyPasswordChangeCode,
  type ProfileResponse,
} from '../../../../services/auth';
import {
  fetchMyTickets,
  fetchRegistrationOptions,
  resendTicketEmail,
  type EventRegistrationOptions,
  type Registration,
} from '../../../../features/events/api';
import {getAuthApiErrorMessage} from '../../shared/apiErrors';

export const useAccountDashboard = () => {
  const {isAuthenticated, logout, user, requiresProfileCompletion} = useAuth();
  const navigate = useNavigate();
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileImage, setProfileImage] = useState<string | null>(null);
  const [imageUploading, setImageUploading] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);
  const [firstName, setFirstName] = useState('');
  const [middleName, setMiddleName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organization, setOrganization] = useState('');
  const [title, setTitle] = useState('');
  const [organizationType, setOrganizationType] = useState<'individual' | 'organization'>('individual');
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [passwordCodeRequested, setPasswordCodeRequested] = useState(false);
  const [passwordCode, setPasswordCode] = useState('');
  const [passwordVerificationToken, setPasswordVerificationToken] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [deleteCodeRequested, setDeleteCodeRequested] = useState(false);
  const [deleteCode, setDeleteCode] = useState('');
  const [deleteVerificationToken, setDeleteVerificationToken] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [tickets, setTickets] = useState<Registration[]>([]);
  const [ticketsLoading, setTicketsLoading] = useState(true);
  const [liveEventOptions, setLiveEventOptions] = useState<EventRegistrationOptions | null>(null);
  const [liveEventLoading, setLiveEventLoading] = useState(true);
  const [resendingId, setResendingId] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/login', {replace: true});
      return;
    }
    if (requiresProfileCompletion) navigate('/complete-profile', {replace: true});
  }, [isAuthenticated, navigate, requiresProfileCompletion]);

  const applyProfile = useCallback((data: ProfileResponse) => {
    setProfile(data);
    setFirstName(data.first_name ?? '');
    setMiddleName(data.middle_name ?? '');
    setLastName(data.last_name ?? '');
    const org = data.organization ?? '';
    const isIndividual = !org || ['individual', 'personal'].includes(org.toLowerCase());
    setOrganizationType(isIndividual ? 'individual' : 'organization');
    setOrganization(isIndividual ? '' : org);
    setTitle(data.title ?? '');
    setProfileError(null);
    if (data.profile_image) setProfileImage(data.profile_image);
  }, []);

  const loadProfile = useCallback(async () => {
    setProfileLoading(true);
    try {
      applyProfile(await getProfile());
    } catch (err: unknown) {
      console.error('[AccountPage] Profile fetch failed:', err);
      setProfileError(getAuthApiErrorMessage(err));
    } finally {
      setProfileLoading(false);
    }
  }, [applyProfile]);

  useEffect(() => {
    if (!isAuthenticated || requiresProfileCompletion) return;
    void loadProfile();
  }, [isAuthenticated, requiresProfileCompletion, loadProfile]);

  useEffect(() => {
    if (!isAuthenticated || requiresProfileCompletion) return;
    const loadTickets = async () => {
      try {
        setTickets(await fetchMyTickets());
      } catch {
        // Non-critical.
      } finally {
        setTicketsLoading(false);
      }
    };
    void loadTickets();
  }, [isAuthenticated, requiresProfileCompletion]);

  useEffect(() => {
    if (!isAuthenticated || requiresProfileCompletion) return;
    const loadLiveEvent = async () => {
      try {
        setLiveEventOptions(await fetchRegistrationOptions());
      } catch {
        setLiveEventOptions(null);
      } finally {
        setLiveEventLoading(false);
      }
    };
    void loadLiveEvent();
  }, [isAuthenticated, requiresProfileCompletion]);

  const handleResendTicketEmail = async (registrationId: string) => {
    setResendingId(registrationId);
    try {
      await resendTicketEmail(registrationId);
      setTickets(await fetchMyTickets());
    } finally {
      setResendingId(null);
    }
  };

  const handleImageChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) return setImageError('Please select an image file.');
    if (file.size > 5 * 1024 * 1024) return setImageError('Image size should be less than 5MB.');

    setImageUploading(true);
    setImageError(null);
    setProfileMessage(null);
    try {
      applyProfile(await uploadProfileImage(file));
      setProfileMessage('Profile image updated successfully.');
      event.target.value = '';
    } catch (err: unknown) {
      setImageError(getAuthApiErrorMessage(err));
    } finally {
      setImageUploading(false);
    }
  };

  const handleProfileSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setProfileSaving(true);
    setProfileMessage(null);
    setProfileError(null);
    try {
      const orgValue = organizationType === 'individual' ? 'Individual' : organization.trim();
      const titleValue = organizationType === 'organization' ? title.trim() : '';
      const updated = await updateProfileFields({
        first_name: firstName.trim(),
        middle_name: middleName.trim(),
        last_name: lastName.trim(),
        organization: orgValue,
        title: titleValue,
      });
      setProfile(updated);
      setProfileMessage('Profile updated successfully.');
      setIsEditingProfile(false);
    } catch (err: unknown) {
      setProfileError(getAuthApiErrorMessage(err));
    } finally {
      setProfileSaving(false);
    }
  };

  const handleCancelEditing = () => {
    setIsEditingProfile(false);
    setFirstName(profile?.first_name || '');
    setMiddleName(profile?.middle_name || '');
    setLastName(profile?.last_name || '');
    const org = profile?.organization || '';
    const isIndividual = !org || ['individual', 'personal'].includes(org.toLowerCase());
    setOrganizationType(isIndividual ? 'individual' : 'organization');
    setOrganization(isIndividual ? '' : org);
    setTitle(profile?.title || '');
    setProfileMessage(null);
    setProfileError(null);
  };

  const clearPasswordFeedback = useCallback(() => {
    setPasswordMessage(null);
    setPasswordError(null);
  }, []);

  const clearDeleteFeedback = useCallback(() => {
    setDeleteMessage(null);
    setDeleteError(null);
  }, []);

  const resetPasswordForm = useCallback(() => {
    setPasswordCodeRequested(false);
    setPasswordCode('');
    setPasswordVerificationToken(null);
    setNewPassword('');
    setConfirmPassword('');
  }, []);

  const resetDeleteForm = useCallback(() => {
    setDeleteCodeRequested(false);
    setDeleteCode('');
    setDeleteVerificationToken(null);
  }, []);

  const getPasswordEmail = useCallback(() => profile?.email || user?.email || '', [profile?.email, user?.email]);

  const handlePasswordRequestCode = async () => {
    const email = getPasswordEmail();
    if (!email) {
      setPasswordError('No account email is available for password verification.');
      return;
    }

    setPasswordLoading(true);
    clearPasswordFeedback();
    setPasswordVerificationToken(null);
    setNewPassword('');
    setConfirmPassword('');

    try {
      const response = await requestPasswordChangeCode(email);
      setPasswordCodeRequested(true);
      setPasswordCode('');
      setPasswordMessage(response.message || 'Verification code sent.');
    } catch (err: unknown) {
      setPasswordError(getAuthApiErrorMessage(err));
    } finally {
      setPasswordLoading(false);
    }
  };

  const handlePasswordVerifyCode = async (event: FormEvent) => {
    event.preventDefault();
    const email = getPasswordEmail();
    if (!email) {
      setPasswordError('No account email is available for password verification.');
      return;
    }

    setPasswordLoading(true);
    clearPasswordFeedback();

    try {
      const response = await verifyPasswordChangeCode(email, passwordCode);
      setPasswordVerificationToken(response.verification_token);
      setPasswordMessage(response.message || 'Code verified. You can now enter a new password.');
    } catch (err: unknown) {
      setPasswordError(getAuthApiErrorMessage(err));
    } finally {
      setPasswordLoading(false);
    }
  };

  const handlePasswordConfirm = async (event: FormEvent) => {
    event.preventDefault();
    if (!passwordVerificationToken) {
      setPasswordError('Verify your code before changing your password.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match.');
      return;
    }

    setPasswordLoading(true);
    clearPasswordFeedback();

    try {
      const response = await confirmPasswordChange(passwordVerificationToken, newPassword, confirmPassword);
      resetPasswordForm();
      setPasswordMessage(response.message || 'Password changed successfully.');
    } catch (err: unknown) {
      setPasswordError(getAuthApiErrorMessage(err));
    } finally {
      setPasswordLoading(false);
    }
  };

  const handleDeleteRequestCode = async () => {
    setDeleteLoading(true);
    clearDeleteFeedback();
    setDeleteVerificationToken(null);

    try {
      const response = await requestAccountDeletionCode();
      setDeleteCodeRequested(true);
      setDeleteCode('');
      setDeleteMessage(response.message || 'Deletion verification code sent.');
    } catch (err: unknown) {
      setDeleteError(getAuthApiErrorMessage(err));
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleDeleteVerifyCode = async (event: FormEvent) => {
    event.preventDefault();
    setDeleteLoading(true);
    clearDeleteFeedback();

    try {
      const response = await verifyAccountDeletionCode(deleteCode);
      setDeleteVerificationToken(response.verification_token);
      setDeleteMessage(response.message || 'Deletion code verified.');
    } catch (err: unknown) {
      setDeleteError(getAuthApiErrorMessage(err));
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleDeleteConfirm = async (event: FormEvent) => {
    event.preventDefault();
    if (!deleteVerificationToken) {
      setDeleteError('Verify your deletion code before deleting your account.');
      return;
    }

    setDeleteLoading(true);
    clearDeleteFeedback();

    try {
      const response = await confirmAccountDeletion(deleteVerificationToken);
      resetDeleteForm();
      setDeleteMessage(response.message || 'Account deleted successfully.');
      logout();
      navigate('/login', {replace: true});
    } catch (err: unknown) {
      setDeleteError(getAuthApiErrorMessage(err));
    } finally {
      setDeleteLoading(false);
    }
  };

  return {
    canRender: isAuthenticated && !requiresProfileCompletion,
    displayEmail: profile?.email || user?.email,
    imageError,
    imageUploading,
    isEditingProfile,
    logout,
    organization,
    organizationType,
    title,
    profile,
    profileError,
    profileImage,
    profileLoading,
    profileMessage,
    profileSaving,
    passwordCodeRequested,
    passwordCode,
    passwordVerificationToken,
    newPassword,
    confirmPassword,
    passwordLoading,
    passwordMessage,
    passwordError,
    deleteCodeRequested,
    deleteCode,
    deleteVerificationToken,
    deleteLoading,
    deleteMessage,
    deleteError,
    resendingId,
    firstName,
    lastName,
    middleName,
    tickets,
    ticketsLoading,
    liveEventOptions,
    liveEventLoading,
    setProfile,
    setFirstName,
    setMiddleName,
    setLastName,
    setPasswordCode,
    setNewPassword,
    setConfirmPassword,
    setDeleteCode,
    setOrganization,
    setOrganizationType,
    setTitle,
    setIsEditingProfile,
    handlePasswordConfirm,
    handlePasswordRequestCode,
    handlePasswordVerifyCode,
    handleDeleteRequestCode,
    handleDeleteVerifyCode,
    handleDeleteConfirm,
    handleCancelEditing,
    handleImageChange,
    handleProfileSubmit,
    handleResendTicketEmail,
    loadProfile,
  };
};
