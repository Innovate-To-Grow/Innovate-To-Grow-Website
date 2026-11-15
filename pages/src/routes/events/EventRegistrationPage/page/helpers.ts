export type EventRegistrationStep = 'loading' | 'select' | 'email' | 'code' | 'form' | 'done';

const STEP_INDEX: Partial<Record<EventRegistrationStep, number>> = {
  select: 0,
  email: 1,
  code: 1,
  form: 2,
  done: 3,
};

/** Where a registration step sits in the four-step progress row (null while loading). */
export function getRegistrationStepIndex(step: EventRegistrationStep): number | null {
  return STEP_INDEX[step] ?? null;
}

const isShortMessage = (value: unknown): value is string => typeof value === 'string' && value.length <= 300;

/** The first field's message: a short string, or the first string of its list. */
const firstFieldMessage = (data: Record<string, unknown>): string | null => {
  const firstKey = Object.keys(data)[0];
  if (!firstKey) return null;
  const value = data[firstKey];
  const candidate = Array.isArray(value) ? value[0] : value;
  return isShortMessage(candidate) ? candidate : null;
};

export function getRegistrationErrorMessage(err: unknown): string {
  const data =
    typeof err === 'object' && err !== null
      ? (err as {response?: {data?: Record<string, unknown>}}).response?.data
      : undefined;
  if (data) {
    if (isShortMessage(data.detail)) return data.detail;
    if (isShortMessage(data.message)) return data.message;
    const message = firstFieldMessage(data);
    if (message) return message;
  }

  return 'An unexpected error occurred. Please try again.';
}

export function normalizeRegistrationEmail(value: string): string {
  return value.trim().toLowerCase();
}

export function getSecondaryEmailError(value: string, primaryEmail: string): string | null {
  const email = normalizeRegistrationEmail(value);
  if (!email) return null;
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return 'Enter a valid secondary email address.';
  }
  if (email === normalizeRegistrationEmail(primaryEmail)) {
    return 'Secondary email must be different from the primary email.';
  }
  return null;
}
