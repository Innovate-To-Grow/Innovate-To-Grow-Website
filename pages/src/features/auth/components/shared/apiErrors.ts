import {isSafeMessage} from '../context/shared';
import {VerificationFlowError} from '@/features/auth/verification/errors';

/** Generic message for account UI where we avoid exposing backend / vendor details (e.g. SMS config). */
export const USER_FACING_GENERIC_ERROR = 'An unknown error occurred.';

export function getAuthApiErrorMessage(err: unknown): string {
  if (err instanceof VerificationFlowError && isSafeMessage(err.message)) return err.message;
  if (typeof err === 'object' && err !== null) {
    const axiosError = err as {response?: {data?: Record<string, unknown>}};
    if (axiosError.response?.data) {
      const data = axiosError.response.data;
      if (typeof data.detail === 'string' && isSafeMessage(data.detail)) return data.detail;
      const firstKey = Object.keys(data).find((key) => !['code', 'request_id', 'challenge_id', 'retry_after'].includes(key));
      if (firstKey) {
        const value = data[firstKey];
        if (Array.isArray(value) && typeof value[0] === 'string' && isSafeMessage(value[0])) return value[0];
        if (typeof value === 'string' && isSafeMessage(value)) return value;
      }
    }
  }

  return 'An unexpected error occurred. Please try again.';
}
