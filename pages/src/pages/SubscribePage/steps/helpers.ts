export type SubscribeStep = 'email' | 'code' | 'profile' | 'done';

export function getSubscribeErrorMessage(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const axiosError = err as {response?: {data?: Record<string, unknown>}};
    if (axiosError.response?.data) {
      const data = axiosError.response.data;
      if (typeof data.detail === 'string') return data.detail;
      if (typeof data.message === 'string') return data.message;

      const messages: string[] = [];
      for (const value of Object.values(data)) {
        if (Array.isArray(value)) {
          for (const item of value) {
            if (typeof item === 'string') messages.push(item);
          }
        } else if (typeof value === 'string') {
          messages.push(value);
        }
      }

      if (messages.length > 0) return messages.join(' ');
    }
  }

  return 'An unexpected error occurred. Please try again.';
}
