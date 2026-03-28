export type VerifyFlow = 'auth' | 'login' | 'register' | 'reset' | 'change';

export const FLOW_META: Record<VerifyFlow, {title: string; subtitle: string; buttonLabel: string}> = {
  auth: {
    title: 'Verify Your Email',
    subtitle: 'Enter the 6-digit code we sent to continue signing in or setting up your account.',
    buttonLabel: 'Continue',
  },
  login: {
    title: 'Verify Login',
    subtitle: 'Enter the 6-digit code we sent to finish signing in.',
    buttonLabel: 'Verify and Sign In',
  },
  register: {
    title: 'Verify Your Email',
    subtitle: 'Enter the 6-digit code to activate your new account.',
    buttonLabel: 'Verify and Activate',
  },
  reset: {
    title: 'Reset Password',
    subtitle: 'Enter the 6-digit code to continue resetting your password.',
    buttonLabel: 'Verify Code',
  },
  change: {
    title: 'Confirm Password Change',
    subtitle: 'Enter the 6-digit code we sent before setting a new password.',
    buttonLabel: 'Verify Code',
  },
};

export const isVerifyFlow = (value: string | null): value is VerifyFlow =>
  value === 'auth' || value === 'login' || value === 'register' || value === 'reset' || value === 'change';
