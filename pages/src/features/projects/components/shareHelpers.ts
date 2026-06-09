// Pull a specific message out of a DRF validation error ({field: ["..."]}) so a failed share
// surfaces the actual reason (e.g. the row/name limit) instead of a generic retry prompt.
// Row-level errors (e.g. the row-count limit) surface nested under `rows`.
export const getShareErrorMessage = (error: unknown): string => {
  const data = (error as {response?: {data?: unknown}}).response?.data;
  if (data && typeof data === 'object') {
    for (const field of ['rows', 'name', 'note', 'detail'] as const) {
      const value = (data as Record<string, unknown>)[field];
      const message = Array.isArray(value) ? value[0] : value;
      if (typeof message === 'string' && message.trim()) {
        return message;
      }
    }
  }
  return 'Unable to create a shareable URL. Please try again.';
};

export const getExportFileBaseName = (title: string) => {
  const slug = title
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug ? `past-projects-${slug}` : 'past-projects';
};
