import { useCallback, type Dispatch, type SetStateAction } from 'react';

import type { LoginResponse, User } from '@/features/auth/api';

import { dispatchAuthStateChange, getAuthErrorMessage } from './shared';

export interface AuthStateSetters {
  setUser: Dispatch<SetStateAction<User | null>>;
  setRequiresProfileCompletion: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string | null>>;
  setIsLoading: Dispatch<SetStateAction<boolean>>;
}

/** Shared plumbing of every auth action: loading/error state around a request, and applying a login. */
export function useAuthRequest({ setUser, setRequiresProfileCompletion, setError, setIsLoading }: AuthStateSetters) {
  const applyAuthResponse = useCallback(<T extends LoginResponse,>(response: T): T => {
    setUser(response.user);
    setRequiresProfileCompletion(Boolean(response.requires_profile_completion));
    dispatchAuthStateChange();
    return response;
  }, [setRequiresProfileCompletion, setUser]);

  const runWithErrorHandling = useCallback(async <T, >(callback: () => Promise<T>): Promise<T> => {
    setError(null);
    setIsLoading(true);
    try {
      return await callback();
    } catch (err: unknown) {
      setError(getAuthErrorMessage(err));
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [setError, setIsLoading]);

  return { applyAuthResponse, runWithErrorHandling };
}

export type AuthRequest = ReturnType<typeof useAuthRequest>;
