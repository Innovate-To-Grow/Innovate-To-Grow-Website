import {useCallback, useEffect, useRef, useState, type FormEvent} from 'react';
import {getProfile, getStoredSession, isCurrentSession, updateProfileFields, useAuth} from '@/features/auth';
import {hasRequiredNameFields} from '@/features/auth/api/profileCompletion';
import type {ProfileResponse} from '@/features/auth/api/types';
import {getSubscribeErrorMessage} from '../steps/helpers';
import type {LoadState, OrganizationType, SubscribeWizardStep} from './types';

interface UseSubscriberProfileOptions {
  step: SubscribeWizardStep;
  isAuthenticated: boolean;
  /** Load straight away (the page opened on the profile step). */
  initiallyLoading: boolean;
  setProfile: (profile: ProfileResponse) => void;
  setStep: (step: SubscribeWizardStep) => void;
  setError: (message: string | null) => void;
  clearPageError: () => void;
}

type ProfileFields = ReturnType<typeof useProfileFields>['fields'];

/** The saved profile fields: an individual is stored as the organization "Individual", with no title. */
const profilePayload = ({firstName, middleName, lastName, organizationType, organization, title}: ProfileFields) => ({
  first_name: firstName.trim(),
  middle_name: middleName.trim(),
  last_name: lastName.trim(),
  organization: organizationType === 'individual' ? 'Individual' : organization.trim(),
  title: organizationType === 'organization' ? title.trim() : '',
});

/** The form's name and organization fields, filled from a loaded profile. */
function useProfileFields() {
  const [firstName, setFirstName] = useState('');
  const [middleName, setMiddleName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organizationType, setOrganizationType] = useState<OrganizationType>('organization');
  const [organization, setOrganization] = useState('');
  const [title, setTitle] = useState('');

  const applyProfileToForm = useCallback((nextProfile: ProfileResponse) => {
    setFirstName(nextProfile.first_name ?? '');
    setMiddleName(nextProfile.middle_name ?? '');
    setLastName(nextProfile.last_name ?? '');
    const org = nextProfile.organization ?? '';
    const isIndividual = ['individual', 'personal'].includes(org.trim().toLowerCase());
    setOrganizationType(isIndividual ? 'individual' : 'organization');
    setOrganization(isIndividual ? '' : org);
    setTitle(nextProfile.title ?? '');
  }, []);

  /** Switching the organization type starts its fields over. */
  const changeOrganizationType = (value: OrganizationType) => {
    setOrganizationType(value);
    setOrganization('');
    setTitle('');
  };

  return {
    fields: {firstName, middleName, lastName, organizationType, organization, title},
    setFirstName,
    setMiddleName,
    setLastName,
    setOrganization,
    setTitle,
    applyProfileToForm,
    changeOrganizationType,
  };
}

/**
 * The profile step: the member's name and organization, loaded when the step opens and saved together
 * with the newsletter opt-in. Saving completes a profile that sign-in found incomplete.
 */
export function useSubscriberProfile({
  step,
  isAuthenticated,
  initiallyLoading,
  setProfile,
  setStep,
  setError,
  clearPageError,
}: UseSubscriberProfileOptions) {
  const {clearProfileCompletionRequirement} = useAuth();
  const form = useProfileFields();
  const {fields, applyProfileToForm} = form;
  const [saving, setSaving] = useState(false);
  const [loadState, setLoadState] = useState<LoadState>(() => (initiallyLoading ? 'loading' : 'idle'));
  const [loadError, setLoadError] = useState<string | null>(null);
  const requestSequence = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestSequence.current;
    setLoadState('loading');
    setLoadError(null);
    try {
      const nextProfile = await getProfile();
      if (requestId !== requestSequence.current) return;
      setProfile(nextProfile);
      applyProfileToForm(nextProfile);
      setLoadState('ready');
    } catch {
      if (requestId !== requestSequence.current) return;
      setLoadError('Failed to load your profile.');
      setLoadState('error');
    }
  }, [applyProfileToForm, setProfile]);

  useEffect(() => {
    if (!isAuthenticated || step !== 'profile') return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- starting the explicit async load state is synchronization with the authenticated route step.
    void load();
    return () => {
      requestSequence.current += 1;
    };
  }, [step, isAuthenticated, load]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    clearPageError();
    setSaving(true);
    try {
      const session = getStoredSession();
      if (!session) {
        setError('Your session changed. Reload the page and try again.');
        return;
      }
      const updated = await updateProfileFields({...profilePayload(fields), email_subscribe: true});
      // A sign-out or account switch while saving: this page no longer speaks for that session.
      if (!isCurrentSession({generation: session.generation})) {
        return;
      }
      if (hasRequiredNameFields(updated) && !clearProfileCompletionRequirement({generation: session.generation})) {
        return;
      }
      setProfile(updated);
      setStep('manage');
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  // Every edit clears a shown error; switching the organization type starts its fields over.
  const edit = (setter: (value: string) => void) => (value: string) => {
    setter(value);
    clearPageError();
  };
  const changeOrganizationType = (value: OrganizationType) => {
    form.changeOrganizationType(value);
    clearPageError();
  };

  return {
    fields,
    onFirstNameChange: edit(form.setFirstName),
    onMiddleNameChange: edit(form.setMiddleName),
    onLastNameChange: edit(form.setLastName),
    onOrganizationChange: edit(form.setOrganization),
    onTitleChange: edit(form.setTitle),
    onOrganizationTypeChange: changeOrganizationType,
    saving,
    loadState,
    loadError,
    load,
    handleSubmit,
  };
}
