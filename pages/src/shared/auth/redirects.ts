export const getSafeInternalRedirectPath = (value: string | null | undefined): string | null => {
  const normalized = value?.trim() ?? '';

  if (!normalized || !normalized.startsWith('/') || normalized.startsWith('//')) {
    return null;
  }

  return normalized;
};
