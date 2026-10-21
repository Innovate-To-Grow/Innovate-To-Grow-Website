import { useEffect } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router';
import { getSafeInternalRedirectPath } from '@/features/auth/api/redirects';
import { useAuth } from '../AuthContext';
import { VerifyEmailView } from './verify/VerifyEmailView';
import { FLOW_META, isVerifyFlow, type VerifyFlow } from './verify/shared';
import { useVerifyEmailFlow } from './verify/useVerifyEmailFlow';

const SIGN_IN_FLOWS = new Set<string | null>(['auth', 'login', 'register']);

/** Where the visitor belongs instead of this step, or null to show it. */
const verifyRedirect = (
  flow: VerifyFlow,
  isAuthenticated: boolean,
  requiresProfileCompletion: boolean,
  returnTo: string | null,
): string | null => {
  if (flow === 'change' && !isAuthenticated) return '/login';
  if (SIGN_IN_FLOWS.has(flow) && isAuthenticated) {
    return returnTo ?? (requiresProfileCompletion ? '/complete-profile' : '/account');
  }
  return null;
};

export const VerifyEmailPage = () => {
  const { isAuthenticated, requiresProfileCompletion } = useAuth();
  const [searchParams] = useSearchParams();

  const flowParam = searchParams.get('flow');
  const email = searchParams.get('email')?.trim().toLowerCase() ?? '';
  // returnTo is honored for the sign-in flows (auth/login) and registration, so a login
  // started from a gated page (e.g. Past Projects) lands the user back where they began.
  const returnTo = SIGN_IN_FLOWS.has(flowParam) ? getSafeInternalRedirectPath(searchParams.get('returnTo')) : null;

  if (!isVerifyFlow(flowParam) || !email) {
    return <Navigate to="/login" replace />;
  }
  const redirect = verifyRedirect(flowParam, isAuthenticated, requiresProfileCompletion, returnTo);
  if (redirect) {
    return <Navigate to={redirect} replace />;
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
  const { error, isLoading, clearError } = useAuth();
  const navigate = useNavigate();
  const step = useVerifyEmailFlow({ flow, email, returnTo, initialMessage, onSignedIn });

  useEffect(() => {
    clearError();
  }, [clearError]);

  const meta = FLOW_META[flow];
  const backPath = flow === 'change' ? '/account' : flow === 'reset' ? '/forgot-password' : '/login';

  return (
    <VerifyEmailView
      flow={flow}
      email={email}
      title={meta.title}
      subtitle={meta.subtitle}
      buttonLabel={meta.buttonLabel}
      code={step.code}
      verificationToken={step.verificationToken}
      newPassword={step.newPassword}
      confirmPassword={step.confirmPassword}
      localMessage={step.localMessage}
      localSuccess={step.localSuccess}
      error={error}
      isLoading={isLoading}
      autoFocus={autoFocus}
      hint={hint}
      onCodeChange={(value) => {
        step.setCode(value);
        clearError();
      }}
      onNewPasswordChange={(value) => {
        step.setNewPassword(value);
        clearError();
      }}
      onConfirmPasswordChange={(value) => {
        step.setConfirmPassword(value);
        clearError();
      }}
      onVerifySubmit={step.handleVerify}
      onPasswordSubmit={step.handlePasswordSubmit}
      onResend={step.handleResend}
      onBack={onBack ?? (() => navigate(backPath))}
    />
  );
};
