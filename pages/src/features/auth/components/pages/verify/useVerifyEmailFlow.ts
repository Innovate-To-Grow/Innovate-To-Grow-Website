import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';
import { getPostAuthPath } from '@/features/auth/api/redirects';
import type { LoginResponse } from '@/features/auth/api';
import { useAuth } from '../../AuthContext';
import type { VerifyFlow } from './shared';

type SignInFlow = Extract<VerifyFlow, 'auth' | 'login' | 'register'>;

const isSignInFlow = (flow: VerifyFlow): flow is SignInFlow => flow === 'auth' || flow === 'login' || flow === 'register';

interface UseVerifyEmailFlowOptions {
  flow: VerifyFlow;
  email: string;
  returnTo: string | null;
  initialMessage: string | null;
  onSignedIn?: () => void;
}

/**
 * The emailed-code step of every email flow: sign in (auth / login / register) or, for a password
 * reset or change, verify the code and then set the new password.
 */
export const useVerifyEmailFlow = ({ flow, email, returnTo, initialMessage, onSignedIn }: UseVerifyEmailFlowOptions) => {
  const auth = useAuth();
  const navigate = useNavigate();

  const [code, setCode] = useState('');
  const [verificationToken, setVerificationToken] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [localMessage, setLocalMessage] = useState<string | null>(initialMessage);
  const [localSuccess, setLocalSuccess] = useState<string | null>(null);

  const resetMessages = () => {
    setLocalMessage(null);
    setLocalSuccess(null);
  };

  /** Where a code that signed the visitor in leads; a new registration may first need the profile completed. */
  const signedInPath = (response: LoginResponse & { next_step?: string }) => {
    if (flow !== 'register') return getPostAuthPath(response, returnTo);
    return response.next_step === 'complete_profile' ? getPostAuthPath(response) : (returnTo ?? getPostAuthPath(response));
  };

  const verifySignIn = (signInFlow: SignInFlow) => {
    const verifiers = {
      auth: auth.verifyEmailAuthCode,
      login: auth.verifyLoginCode,
      register: auth.verifyRegistrationCode,
    };
    return verifiers[signInFlow](email, code);
  };

  const handleVerify = async (event: FormEvent) => {
    event.preventDefault();
    resetMessages();
    try {
      if (isSignInFlow(flow)) {
        const response = await verifySignIn(flow);
        onSignedIn?.();
        navigate(signedInPath(response), { replace: true });
        return;
      }
      const verify = flow === 'reset' ? auth.verifyPasswordResetCode : auth.verifyPasswordChangeCode;
      const response = await verify(email, code);
      setVerificationToken(response.verification_token);
      setLocalMessage('Code verified. Set your new password below.');
    } catch {
      // handled by context
    }
  };

  const handleResend = async () => {
    resetMessages();
    const requests: Record<VerifyFlow, () => Promise<{ message: string }>> = {
      auth: () => auth.requestEmailAuthCode(email, 'login'),
      login: () => auth.requestLoginCode(email),
      register: () => auth.resendRegistrationCode(email),
      reset: () => auth.requestPasswordReset(email),
      change: () => auth.requestPasswordChangeCode(email),
    };
    try {
      const response = await requests[flow]();
      setLocalMessage(response.message);
    } catch {
      // handled by context
    }
  };

  const handlePasswordSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!verificationToken) return;
    resetMessages();
    try {
      const response =
        flow === 'reset'
          ? await auth.confirmPasswordReset(email, verificationToken, newPassword, confirmPassword)
          : await auth.confirmPasswordChange(verificationToken, newPassword, confirmPassword);
      setLocalSuccess(response.message);
      const next = flow === 'reset' ? '/login' : '/account';
      window.setTimeout(() => navigate(next, { replace: true }), 900);
    } catch {
      // handled by context
    }
  };

  return {
    code,
    setCode,
    verificationToken,
    newPassword,
    setNewPassword,
    confirmPassword,
    setConfirmPassword,
    localMessage,
    localSuccess,
    handleVerify,
    handleResend,
    handlePasswordSubmit,
  };
};
