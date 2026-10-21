import {isSafeMessage} from '../context/shared';
import {VerificationFlowError} from '@/features/auth/verification/errors';

/** Generic message for account UI where we avoid exposing backend / vendor details (e.g. SMS config). */
export const USER_FACING_GENERIC_ERROR = 'An unknown error occurred.';

const NON_MESSAGE_KEYS = ['code', 'request_id', 'challenge_id', 'retry_after'];

const responseData = (err: unknown): Record<string, unknown> | undefined =>
  typeof err === 'object' && err !== null ? (err as {response?: {data?: Record<string, unknown>}}).response?.data : undefined;

/** The safe message of the first non-metadata field (a string, or the first string of a list). */
const firstFieldMessage = (data: Record<string, unknown>): string | null => {
  const firstKey = Object.keys(data).find((key) => !NON_MESSAGE_KEYS.includes(key));
  if (!firstKey) return null;
  const value = data[firstKey];
  const candidate = Array.isArray(value) ? value[0] : value;
  return typeof candidate === 'string' && isSafeMessage(candidate) ? candidate : null;
};

export function getAuthApiErrorMessage(err: unknown): string {
  if (err instanceof VerificationFlowError && isSafeMessage(err.message)) return err.message;
  const data = responseData(err);
  if (data) {
    if (typeof data.detail === 'string' && isSafeMessage(data.detail)) return data.detail;
    const message = firstFieldMessage(data);
    if (message) return message;
  }

  return 'An unexpected error occurred. Please try again.';
}
