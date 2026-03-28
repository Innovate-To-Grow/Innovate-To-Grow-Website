import {useCallback, useEffect, useState, type ChangeEvent, type FormEvent} from 'react';
import {useNavigate} from 'react-router-dom';
import {useAuth} from '../../AuthContext';
import {getProfile, updateProfileFields, uploadProfileImage, type ProfileResponse} from '../../../../services/auth';
import {fetchMyTickets, resendTicketEmail, type Registration} from '../../../../features/events/api';
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
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [tickets, setTickets] = useState<Registration[]>([]);
  const [ticketsLoading, setTicketsLoading] = useState(true);
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
    setOrganization(data.organization ?? '');
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
      const updated = await updateProfileFields({
        first_name: firstName.trim(),
        middle_name: middleName.trim(),
        last_name: lastName.trim(),
        organization: organization.trim(),
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
    setOrganization(profile?.organization || '');
    setProfileMessage(null);
    setProfileError(null);
  };

  return {
    canRender: isAuthenticated && !requiresProfileCompletion,
    displayEmail: profile?.email || user?.email,
    imageError,
    imageUploading,
    isEditingProfile,
    logout,
    organization,
    profile,
    profileError,
    profileImage,
    profileLoading,
    profileMessage,
    profileSaving,
    resendingId,
    firstName,
    lastName,
    middleName,
    tickets,
    ticketsLoading,
    setProfile,
    setFirstName,
    setMiddleName,
    setLastName,
    setOrganization,
    setIsEditingProfile,
    handleCancelEditing,
    handleImageChange,
    handleProfileSubmit,
    handleResendTicketEmail,
    loadProfile,
  };
};
