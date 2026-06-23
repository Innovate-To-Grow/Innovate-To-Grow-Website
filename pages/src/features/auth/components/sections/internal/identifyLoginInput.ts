/**
 * Decide whether a single login field holds an email address or a US phone
 * number, so one "Email or phone number" input can drive either passwordless
 * flow (email code vs SMS code).
 */
import { canSubmitNationalPhone, parsePhoneInputToNationalDigits } from './phoneInput';

/** Same shape the register form uses — requires a dotted domain. */
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export type LoginInputKind =
  | { type: 'email'; value: string }
  | { type: 'phone'; nationalDigits: string }
  | { type: 'invalid' };

/**
 * Classify a raw login identifier. Rules, checked in order:
 *  - contains "@"      → email attempt (valid only if it matches EMAIL_RE)
 *  - contains a letter → a malformed email, never a phone → invalid
 *  - otherwise         → phone attempt (valid only as 10 US national digits)
 *
 * Returns the cleaned value the matching flow expects: a trimmed email, or the
 * 10 national digits for phone.
 */
export function identifyLoginInput(raw: string): LoginInputKind {
  const value = raw.trim();
  if (!value) return { type: 'invalid' };

  if (value.includes('@')) {
    return EMAIL_RE.test(value) ? { type: 'email', value } : { type: 'invalid' };
  }

  if (/[a-zA-Z]/.test(value)) {
    return { type: 'invalid' };
  }

  const nationalDigits = parsePhoneInputToNationalDigits(value);
  if (canSubmitNationalPhone(nationalDigits)) {
    return { type: 'phone', nationalDigits };
  }

  return { type: 'invalid' };
}
