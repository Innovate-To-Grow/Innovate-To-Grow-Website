import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router';
import { getPostAuthPath, getSafeInternalRedirectPath } from '@/features/auth/api/redirects';
import { useAuth } from '../AuthContext';
import { VerifyEmailView } from './verify/VerifyEmailView';
import { FLOW_META, isVerifyFlow, type VerifyFlow } from './verify/shared';

export const VerifyEmailPage = () => {
  const { isAuthenticated, requiresProfileCompletion } = useAuth();
  const [searchParams] = useSearchParams();

  const flowParam = searchParams.get('flow');
  const email = searchParams.get('email')?.trim().toLowerCase() ?? '';
  // returnTo is honored for the sign-in flows (auth/login) and registration, so a login
  // started from a gated page (e.g. Past Projects) lands the user back where they began.
  const returnTo =
    flowParam === 'register' || flowParam === 'auth' || flowParam === 'login'
      ? getSafeInternalRedirectPath(searchParams.get('returnTo'))
      : null;

  if (!isVerifyFlow(flowParam) || !email) {
    return <Navigate to="/login" replace />;
  }

  if (flowParam === 'change' && !isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if ((flowParam === 'auth' || flowParam === 'login' || flowParam === 'register') && isAuthenticated) {
    return <Navigate to={returnTo ?? (requiresProfileCompletion ? '/complete-profile' : '/account')} replace />;
  }

  return <VerifyEmailPageContent key={`${flowParam}:${email}:${returnTo ?? ''}`} flow={flowParam} email={email} returnTo={returnTo} />;
};

interface VerifyEmailPageContentProps {
  flow: VerifyFlow;
  email: string;
  returnTo: string | null;
  /**
   * What the "Back" link does. Defaults to leaving for the flow's own entry
   * page; a host that renders this inline (no route of its own) supplies its
   * own step back instead.
   */
  onBack?: () => void;
  /**
   * Runs once a code has signed the visitor in (the auth, login and register
   * flows), just before navigating on. A host that keeps state about the
   * sign-in it replaced drops it here.
   */
  onSignedIn?: () => void;
  /**
   * Focus the code field on mount. Off by default so the standalone
   * `/verify-email` route is unchanged; a host that swaps this in for the step
   * the visitor was just typing in turns it on, or focus is lost to <body>.
   */
  autoFocus?: boolean;
  /**
   * An info message shown when the step opens, in the place a resend's
   * confirmation later takes (which replaces it). A host that has just
   * requested the code itself passes the server's acknowledgement here.
   */
  initialMessage?: string | null;
  /** Help text under the code field, for as long as the step is open. */
  hint?: string | null;
}

export const VerifyEmailPageContent = ({
  flow,
  email,
  returnTo,
  onBack,
  onSignedIn,
  autoFocus = false,
  initialMessage = null,
  hint = null,
}: VerifyEmailPageContentProps) => {
  const {
    error,
    isLoading,
    requestEmailAuthCode,
    verifyEmailAuthCode,
    clearError,
    verifyLoginCode,
    verifyRegistrationCode,
    resendRegistrationCode,
    requestLoginCode,
    requestPasswordReset,
    verifyPasswordResetCode,
    confirmPasswordReset,
    requestPasswordChangeCode,
    verifyPasswordChangeCode,
    confirmPasswordChange,
  } = useAuth();
  const navigate = useNavigate();

  const [code, setCode] = useState('');
  const [verificationToken, setVerificationToken] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [localMessage, setLocalMessage] = useState<string | null>(initialMessage);
  const [localSuccess, setLocalSuccess] = useState<string | null>(null);

  useEffect(() => {
    clearError();
  }, [clearError]);

  const meta = FLOW_META[flow];

  const handleVerify = async (event: FormEvent) => {
    event.preventDefault();
    setLocalMessage(null);
    setLocalSuccess(null);
    try {
      if (flow === 'auth') {
        const response = await verifyEmailAuthCode(email, code);
        onSignedIn?.();
        navigate(getPostAuthPath(response, returnTo), { replace: true });
        return;
      }
      if (flow === 'login') {
        const response = await verifyLoginCode(email, code);
        onSignedIn?.();
        navigate(getPostAuthPath(response, returnTo), { replace: true });
        return;
      }
      if (flow === 'register') {
        const response = await verifyRegistrationCode(email, code);
        onSignedIn?.();
        navigate(
          response.next_step === 'complete_profile' ? getPostAuthPath(response) : (returnTo ?? getPostAuthPath(response)),
          { replace: true },
        );
        return;
      }
      if (flow === 'reset') {
        const response = await verifyPasswordResetCode(email, code);
        setVerificationToken(response.verification_token);
        setLocalMessage('Code verified. Set your new password below.');
        return;
      }
      const response = await verifyPasswordChangeCode(email, code);
      setVerificationToken(response.verification_token);
      setLocalMessage('Code verified. Set your new password below.');
    } catch {
      // handled by context
    }
  };

  const handleResend = async () => {
    setLocalMessage(null);
    setLocalSuccess(null);
    try {
      if (flow === 'auth') {
        const response = await requestEmailAuthCode(email, 'login');
        setLocalMessage(response.message);
        return;
      }
      if (flow === 'login') {
        const response = await requestLoginCode(email);
        setLocalMessage(response.message);
        return;
      }
      if (flow === 'register') {
        const response = await resendRegistrationCode(email);
        setLocalMessage(response.message);
        return;
      }
      if (flow === 'reset') {
        const response = await requestPasswordReset(email);
        setLocalMessage(response.message);
        return;
      }
      const response = await requestPasswordChangeCode(email);
      setLocalMessage(response.message);
    } catch {
      // handled by context
    }
  };

  const handlePasswordSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!verificationToken) return;
    setLocalMessage(null);
    setLocalSuccess(null);
    try {
      if (flow === 'reset') {
        const response = await confirmPasswordReset(email, verificationToken, newPassword, confirmPassword);
        setLocalSuccess(response.message);
        window.setTimeout(() => navigate('/login', { replace: true }), 900);
        return;
      }
      const response = await confirmPasswordChange(verificationToken, newPassword, confirmPassword);
      setLocalSuccess(response.message);
      window.setTimeout(() => navigate('/account', { replace: true }), 900);
    } catch {
      // handled by context
    }
  };

  return (
    <VerifyEmailView
      flow={flow}
      email={email}
      title={meta.title}
      subtitle={meta.subtitle}
      buttonLabel={meta.buttonLabel}
      code={code}
      verificationToken={verificationToken}
      newPassword={newPassword}
      confirmPassword={confirmPassword}
      localMessage={localMessage}
      localSuccess={localSuccess}
      error={error}
      isLoading={isLoading}
      autoFocus={autoFocus}
      hint={hint}
      onCodeChange={(value) => {
        setCode(value);
        clearError();
      }}
      onNewPasswordChange={(value) => {
        setNewPassword(value);
        clearError();
      }}
      onConfirmPasswordChange={(value) => {
        setConfirmPassword(value);
        clearError();
      }}
      onVerifySubmit={handleVerify}
      onPasswordSubmit={handlePasswordSubmit}
      onResend={handleResend}
      onBack={onBack ?? (() => navigate(flow === 'change' ? '/account' : flow === 'reset' ? '/forgot-password' : '/login'))}
    />
  );
};
