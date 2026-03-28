export function getAuthApiErrorMessage(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const axiosError = err as {response?: {data?: Record<string, unknown>}};
    if (axiosError.response?.data) {
      const data = axiosError.response.data;
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
