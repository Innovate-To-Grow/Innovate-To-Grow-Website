import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';
import { useAuth } from '../AuthContext';
import { getProfile, getStoredSession, isCurrentSession, updateProfileFields } from '@/features/auth/api';
import { getAuthErrorMessage } from '../context/shared';
import { useProfileForm } from '../shared/useProfileForm';

type ProfileForm = ReturnType<typeof useProfileForm>;

/** The first required field that is still empty, as the message to show. */
const missingRequiredField = (form: ProfileForm): string | null => {
  if (!form.firstName.trim()) return 'First name is required.';
  if (!form.lastName.trim()) return 'Last name is required.';
  if (form.organizationType === 'organization' && !form.organization.trim()) return 'Organization name is required.';
  return null;
};

/**
 * Profile completion: load the member's profile into the form (for the current session only), then
 * save it and clear the completion requirement before continuing.
 */
export const useCompleteProfile = (returnTo: string | null) => {
  const { user, isAuthenticated, requiresProfileCompletion, clearProfileCompletionRequirement } = useAuth();
  const navigate = useNavigate();
  const form = useProfileForm();
  const { fillForm } = form;
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !requiresProfileCompletion) {
      return;
    }
    const session = getStoredSession();
    if (!session) return;
    const guard = {
      generation: session.generation,
    };
    let active = true;
    const isLive = () => active && isCurrentSession(guard);

    const loadProfile = async () => {
      await Promise.resolve();
      if (!isLive()) return;
      setIsBootstrapping(true);
      setError(null);
      fillForm(null);
      try {
        const profile = await getProfile();
        if (!isLive()) return;
        fillForm(profile);
      } catch (err: unknown) {
        if (!isLive()) return;
        setError(getAuthErrorMessage(err));
      } finally {
        if (isLive()) {
          setIsBootstrapping(false);
        }
      }
    };

    void loadProfile();
    return () => {
      active = false;
    };
  }, [
    isAuthenticated,
    requiresProfileCompletion,
    user?.member_uuid,
    fillForm,
  ]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const missing = missingRequiredField(form);
    if (missing) {
      setError(missing);
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      const session = getStoredSession();
      if (!session) return;
      const guard = {
        generation: session.generation,
      };
      await updateProfileFields(form.formValues());
      if (!clearProfileCompletionRequirement(guard)) return;
      navigate(returnTo ?? '/account', { replace: true });
    } catch (err: unknown) {
      setError(getAuthErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  return { isAuthenticated, requiresProfileCompletion, form, isBootstrapping, isSaving, error, setError, handleSubmit };
};
