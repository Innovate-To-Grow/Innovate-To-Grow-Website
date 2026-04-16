export type EventRegistrationStep = 'loading' | 'email' | 'code' | 'form' | 'done';

export function formatEventDate(dateStr: string): string {
  const date = new Date(`${dateStr}T00:00:00`);
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

export function getRegistrationErrorMessage(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const axiosError = err as {response?: {data?: Record<string, unknown>}};
    if (axiosError.response?.data) {
      const data = axiosError.response.data;
      if (typeof data.detail === 'string' && data.detail.length <= 300) return data.detail;
      if (typeof data.message === 'string' && data.message.length <= 300) return data.message;
      const firstKey = Object.keys(data)[0];
      if (firstKey) {
        const value = data[firstKey];
        if (Array.isArray(value) && typeof value[0] === 'string' && value[0].length <= 300) return value[0];
        if (typeof value === 'string' && value.length <= 300) return value;
      }
    }
  }

  return 'An unexpected error occurred. Please try again.';
}
