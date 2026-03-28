export type EventRegistrationStep = 'loading' | 'email' | 'code' | 'profile' | 'form' | 'done';

export function formatEventDate(dateStr: string): string {
  const date = new Date(`${dateStr}T00:00:00`);
  return date.toLocaleDateString('en-US', {year: 'numeric', month: 'long', day: 'numeric'});
}

export function getRegistrationErrorMessage(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const axiosError = err as {response?: {data?: Record<string, unknown>}};
    if (axiosError.response?.data) {
      const data = axiosError.response.data;
      if (typeof data.detail === 'string') return data.detail;
      if (typeof data.message === 'string') return data.message;
      const firstKey = Object.keys(data)[0];
      if (firstKey) {
        const value = data[firstKey];
        if (Array.isArray(value)) return value[0] as string;
        if (typeof value === 'string') return value;
      }
    }
  }

  return 'An unexpected error occurred. Please try again.';
}
