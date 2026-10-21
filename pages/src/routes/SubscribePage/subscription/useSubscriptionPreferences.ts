import {useCallback, useEffect, useRef, useState} from 'react';
import {getContactEmails, getContactPhones, getProfile, updateContactEmail, updateContactPhone, updateProfileFields} from '@/features/auth';
import type {ContactEmail, ContactPhone, ProfileResponse} from '@/features/auth/api/types';
import {getSubscribeErrorMessage} from '../steps/helpers';
import type {LoadState, SubscribeWizardStep} from './types';

const preferenceMessage = (kind: 'email' | 'phone', subscribed: boolean) =>
  kind === 'phone'
    ? `Text Messages ${subscribed ? 'enabled' : 'disabled'}.`
    : `Newsletters ${subscribed ? 'enabled' : 'disabled'}.`;

interface UseSubscriptionPreferencesOptions {
  step: SubscribeWizardStep;
  isAuthenticated: boolean;
  /** Load straight away (the page opened on the manage step). */
  initiallyLoading: boolean;
  setProfile: (profile: ProfileResponse) => void;
  setMessage: (message: string | null) => void;
  setError: (message: string | null) => void;
  clearPageError: () => void;
}

/** The manage step: newsletter and text-message opt-ins for the primary email and each contact. */
export function useSubscriptionPreferences({
  step,
  isAuthenticated,
  initiallyLoading,
  setProfile,
  setMessage,
  setError,
  clearPageError,
}: UseSubscriptionPreferencesOptions) {
  const [contactEmails, setContactEmails] = useState<ContactEmail[]>([]);
  const [contactPhones, setContactPhones] = useState<ContactPhone[]>([]);
  const [loadState, setLoadState] = useState<LoadState>(() => (initiallyLoading ? 'loading' : 'idle'));
  const [loadError, setLoadError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const requestSequence = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestSequence.current;
    setLoadState('loading');
    setLoadError(null);
    try {
      const [nextProfile, nextContactEmails, nextContactPhones] = await Promise.all([
        getProfile(),
        getContactEmails(),
        getContactPhones(),
      ]);
      if (requestId !== requestSequence.current) return;
      setProfile(nextProfile);
      setContactEmails(nextContactEmails);
      setContactPhones(nextContactPhones);
      setLoadState('ready');
    } catch {
      if (requestId !== requestSequence.current) return;
      setLoadError('Failed to load subscription preferences.');
      setLoadState('error');
    }
  }, [setProfile]);

  useEffect(() => {
    if (!isAuthenticated || step !== 'manage') return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- starting the explicit async load state is synchronization with the authenticated route step.
    void load();
    return () => {
      requestSequence.current += 1;
    };
  }, [step, isAuthenticated, load]);

  /** Run one toggle: a single save at a time per control, then the confirmation line. */
  const runToggle = async (savingKey: string, kind: 'email' | 'phone', subscribed: boolean, save: () => Promise<void>) => {
    clearPageError();
    setSavingId(savingKey);
    try {
      await save();
      setMessage(preferenceMessage(kind, subscribed));
    } catch (err: unknown) {
      setError(getSubscribeErrorMessage(err));
    } finally {
      setSavingId(null);
    }
  };

  const togglePrimaryEmail = (subscribed: boolean) =>
    runToggle('primary-email', 'email', subscribed, async () => {
      setProfile(await updateProfileFields({email_subscribe: subscribed}));
    });

  const toggleContactEmail = (contact: ContactEmail, subscribed: boolean) =>
    runToggle(`email-${contact.id}`, 'email', subscribed, async () => {
      const updated = await updateContactEmail(contact.id, {subscribe: subscribed});
      setContactEmails((current) => current.map((item) => (item.id === contact.id ? updated : item)));
    });

  const toggleContactPhone = (phone: ContactPhone, subscribed: boolean) =>
    runToggle(`phone-${phone.id}`, 'phone', subscribed, async () => {
      const updated = await updateContactPhone(phone.id, {subscribe: subscribed});
      setContactPhones((current) => current.map((item) => (item.id === phone.id ? updated : item)));
    });

  return {
    contactEmails,
    contactPhones,
    loadState,
    loadError,
    savingId,
    load,
    togglePrimaryEmail,
    toggleContactEmail,
    toggleContactPhone,
  };
}
