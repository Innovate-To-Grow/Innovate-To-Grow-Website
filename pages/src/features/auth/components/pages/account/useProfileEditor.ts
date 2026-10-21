import {useCallback, useEffect, useState, type ChangeEvent, type FormEvent} from 'react';
import {getProfile, updateProfileFields, uploadProfileImage, type ProfileResponse} from '@/features/auth/api';
import {getAuthApiErrorMessage} from '../../shared/apiErrors';
import {useProfileForm} from '../../shared/useProfileForm';

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

/** Validate and upload a new profile image; ``onUploaded`` receives the updated profile. */
function useProfileImageUpload(onUploaded: (updated: ProfileResponse) => void) {
  const [imageUploading, setImageUploading] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);

  const handleImageChange = async (event: ChangeEvent<HTMLInputElement>, beforeUpload: () => void) => {
    const file = event.target.files?.[0];
    if (!file) return false;
    const invalid = !file.type.startsWith('image/')
      ? 'Please select an image file.'
      : file.size > MAX_IMAGE_BYTES
        ? 'Image size should be less than 5MB.'
        : null;
    if (invalid) {
      setImageError(invalid);
      return false;
    }

    setImageUploading(true);
    setImageError(null);
    beforeUpload();
    try {
      onUploaded(await uploadProfileImage(file));
      event.target.value = '';
      return true;
    } catch (err: unknown) {
      setImageError(getAuthApiErrorMessage(err));
      return false;
    } finally {
      setImageUploading(false);
    }
  };

  return {imageUploading, imageError, handleImageChange};
}

/** The profile card: the loaded profile, its edit form, and the profile image upload. */
export function useProfileEditor(enabled: boolean) {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileImage, setProfileImage] = useState<string | null>(null);
  const form = useProfileForm();
  const {fillForm, formValues, ...formFields} = form;
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [isEditingProfile, setIsEditingProfile] = useState(false);

  const applyProfile = useCallback(
    (data: ProfileResponse) => {
      setProfile(data);
      fillForm(data);
      setProfileError(null);
      if (data.profile_image) setProfileImage(data.profile_image);
    },
    [fillForm],
  );

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
    if (!enabled) return;
    // profileLoading starts true (useState), so the mount load skips the
    // synchronous setProfileLoading(true) that loadProfile() does for the retry
    // button. Defining the loader inline keeps every setState behind an await,
    // mirroring the tickets/registration-events effects.
    const loadProfileOnMount = async () => {
      try {
        applyProfile(await getProfile());
      } catch (err: unknown) {
        console.error('[AccountPage] Profile fetch failed:', err);
        setProfileError(getAuthApiErrorMessage(err));
      } finally {
        setProfileLoading(false);
      }
    };
    void loadProfileOnMount();
  }, [enabled, applyProfile]);

  const imageUpload = useProfileImageUpload(applyProfile);
  const handleImageChange = async (event: ChangeEvent<HTMLInputElement>) => {
    if (await imageUpload.handleImageChange(event, () => setProfileMessage(null))) {
      setProfileMessage('Profile image updated successfully.');
    }
  };

  const handleProfileSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setProfileSaving(true);
    setProfileMessage(null);
    setProfileError(null);
    try {
      const updated = await updateProfileFields(formValues());
      setProfile(updated);
      setProfileMessage('Profile updated successfully.');
      setIsEditingProfile(false);
    } catch (err: unknown) {
      setProfileError(getAuthApiErrorMessage(err));
    } finally {
      setProfileSaving(false);
    }
  };

  /** Discard the edits: the form shows the saved profile again. */
  const handleCancelEditing = () => {
    setIsEditingProfile(false);
    fillForm(profile);
    setProfileMessage(null);
    setProfileError(null);
  };

  return {
    profile,
    setProfile,
    profileLoading,
    profileImage,
    imageUploading: imageUpload.imageUploading,
    imageError: imageUpload.imageError,
    ...formFields,
    profileSaving,
    profileMessage,
    profileError,
    isEditingProfile,
    setIsEditingProfile,
    loadProfile,
    handleImageChange,
    handleProfileSubmit,
    handleCancelEditing,
  };
}
