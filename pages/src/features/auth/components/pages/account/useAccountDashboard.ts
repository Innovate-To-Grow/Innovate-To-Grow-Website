import {useCallback, useEffect} from 'react';
import {useNavigate} from 'react-router';
import {useAuth} from '../../AuthContext';
import {firstEmailAddress} from '@/features/auth/components/sections/internal/emailAddress';
import {useAccountDeletion} from './useAccountDeletion';
import {useAccountTickets} from './useAccountTickets';
import {usePasswordChange} from './usePasswordChange';
import {useProfileEditor} from './useProfileEditor';

/**
 * The account page: redirects visitors who cannot use it, then composes one hook per section — the
 * profile card, password change, account deletion, and tickets.
 */
export const useAccountDashboard = () => {
  const {isAuthenticated, isInitializing, logout, user, requiresProfileCompletion} = useAuth();
  const navigate = useNavigate();
  const enabled = isAuthenticated && !requiresProfileCompletion;

  useEffect(() => {
    if (isInitializing) return;
    if (!isAuthenticated) {
      navigate('/login', {replace: true});
      return;
    }
    if (requiresProfileCompletion) navigate('/complete-profile', {replace: true});
  }, [isAuthenticated, isInitializing, navigate, requiresProfileCompletion]);

  const profileEditor = useProfileEditor(enabled);
  const {profile} = profileEditor;

  // Pass the primary email when one exists so the backend can disambiguate; a
  // phone-only account has none, and the backend then sends the code via SMS.
  const getPasswordEmail = useCallback(
    () => firstEmailAddress(profile?.email, user?.email) || undefined,
    [profile?.email, user?.email],
  );
  const password = usePasswordChange(getPasswordEmail);
  const deletion = useAccountDeletion(logout);
  const tickets = useAccountTickets(enabled);

  return {
    canRender: !isInitializing && isAuthenticated && !requiresProfileCompletion,
    displayEmail: firstEmailAddress(profile?.email, user?.email),
    logout,
    ...profileEditor,
    ...password,
    ...deletion,
    ...tickets,
  };
};
