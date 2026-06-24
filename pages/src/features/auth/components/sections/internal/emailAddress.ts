export function normalizeEmailAddress(value?: string | null): string {
  const trimmed = value?.trim() ?? '';
  return trimmed.includes('@') ? trimmed : '';
}

export function firstEmailAddress(...values: Array<string | null | undefined>): string {
  return values.map(normalizeEmailAddress).find(Boolean) ?? '';
}
