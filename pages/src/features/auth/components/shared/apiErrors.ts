import {isSafeMessage} from '../context/shared';

/** Generic message for account UI where we avoid exposing backend / vendor details (e.g. SMS config). */
export const USER_FACING_GENERIC_ERROR = 'An unknown error occurred.';

export function getAuthApiErrorMessage(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const axiosError = err as {response?: {data?: Record<string, unknown>}};
    if (axiosError.response?.data) {
      const data = axiosError.response.data;
      const firstKey = Object.keys(data)[0];
      if (firstKey) {
        const value = data[firstKey];
        if (Array.isArray(value) && typeof value[0] === 'string' && isSafeMessage(value[0])) return value[0];
        if (typeof value === 'string' && isSafeMessage(value)) return value;
      }
    }
  }

  return 'An unexpected error occurred. Please try again.';
}
