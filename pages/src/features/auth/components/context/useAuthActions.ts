import { useCallback, useMemo } from 'react';

import {
  clearProfileCompletionRequired as clearProfileCompletionRequiredStorage,
  getProfile as apiGetProfile,
  logout as apiLogout,
  getStoredSession,
  updateStoredUser,
} from '@/features/auth/api';

import { dispatchAuthStateChange } from './shared';
import { useAuthRequest, type AuthStateSetters } from './useAuthRequest';
import { usePasswordActions } from './usePasswordActions';
import { useSignInActions } from './useSignInActions';

/**
 * Every auth action the context exposes: sign-in, password flows, and session upkeep. The
 * returned object is stable while its callbacks are, so the context value can depend on it.
 */
export function useAuthActions(setters: AuthStateSetters) {
  const { setUser, setRequiresProfileCompletion, setError } = setters;
  const request = useAuthRequest(setters);
  const signIn = useSignInActions(request);
  const passwords = usePasswordActions(request);

  const clearError = useCallback(() => {
    setError(null);
  }, [setError]);

  const logout = useCallback(() => {
    apiLogout();
    setUser(null);
    setRequiresProfileCompletion(false);
    dispatchAuthStateChange();
  }, [setRequiresProfileCompletion, setUser]);

  const clearProfileCompletionRequirement = useCallback((guard?: {generation: string; refresh?: string}) => {
    if (!clearProfileCompletionRequiredStorage(guard)) return false;
    setRequiresProfileCompletion(false);
    dispatchAuthStateChange();
    return true;
  }, [setRequiresProfileCompletion]);

  const refreshProfile = useCallback(async () => {
    const snapshot = getStoredSession();
    if (!snapshot) return;
    try {
      const profile = await apiGetProfile();
      const updated = updateStoredUser(
        (current) => ({...current, profile_image: profile.profile_image}),
        snapshot.generation,
      );
      if (updated) setUser(updated);
    } catch {
      // User may have been logged out; ignore background refresh failures.
    }
  }, [setUser]);

  return useMemo(
    () => ({ ...signIn, ...passwords, clearError, logout, refreshProfile, clearProfileCompletionRequirement }),
    [signIn, passwords, clearError, logout, refreshProfile, clearProfileCompletionRequirement],
  );
}
