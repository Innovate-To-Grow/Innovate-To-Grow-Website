import {collectFieldMessages} from '@/lib/api/errorMessages';

export type SubscribeStep = 'email' | 'code' | 'profile' | 'done';

const MAX_MESSAGE_LENGTH = 300;
const isShortMessage = (value: unknown): value is string =>
  typeof value === 'string' && value.length <= MAX_MESSAGE_LENGTH;

/** `detail`, else `message`, else every field message joined; long (non-user-facing) text is skipped. */
export function getSubscribeErrorMessage(err: unknown): string {
  const data =
    typeof err === 'object' && err !== null
      ? (err as {response?: {data?: Record<string, unknown>}}).response?.data
      : undefined;
  if (data) {
    if (isShortMessage(data.detail)) return data.detail;
    if (isShortMessage(data.message)) return data.message;
    const messages = collectFieldMessages(data, isShortMessage);
    if (messages.length > 0) return messages.join(' ');
  }
  return 'An unexpected error occurred. Please try again.';
}
