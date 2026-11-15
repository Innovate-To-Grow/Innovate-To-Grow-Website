import type {FormEvent} from 'react';
import type {VerifyFlow} from './shared';

export const MESSAGE_ID = 'verify-email-message';
export const HINT_ID = 'verify-email-hint';

/**
 * The code field usually holds focus when the message appears, and a live
 * region inserted together with its text is not reliably announced, so the
 * message and hint are also read as the field's description.
 */
export const describeCodeField = (message: string | null, hint: string | null) =>
  [message ? MESSAGE_ID : null, hint ? HINT_ID : null].filter(Boolean).join(' ') || undefined;

export interface VerifyEmailViewProps {
  flow: VerifyFlow;
  email: string;
  title: string;
  subtitle: string;
  buttonLabel: string;
  code: string;
  verificationToken: string | null;
  newPassword: string;
  confirmPassword: string;
  localMessage: string | null;
  localSuccess: string | null;
  error: string | null;
  isLoading: boolean;
  /** Focus the code field on mount. */
  autoFocus?: boolean;
  /** Help text under the code field (e.g. what to try when no code arrives). */
  hint?: string | null;
  onCodeChange: (value: string) => void;
  onNewPasswordChange: (value: string) => void;
  onConfirmPasswordChange: (value: string) => void;
  onVerifySubmit: (event: FormEvent) => void;
  onPasswordSubmit: (event: FormEvent) => void;
  onResend: () => void;
  onBack: () => void;
}
