import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { getSafeInternalRedirectPath } from '../../../shared/auth/redirects';
import { useAuth } from '../AuthContext';
import { VerifyEmailView } from './verify/VerifyEmailView';
import { FLOW_META, isVerifyFlow, type VerifyFlow } from './verify/shared';
import '../Auth.css';

export const VerifyEmailPage = () => {
  const { isAuthenticated, requiresProfileCompletion } = useAuth();
  const [searchParams] = useSearchParams();

  const flowParam = searchParams.get('flow');
  const email = searchParams.get('email')?.trim().toLowerCase() ?? '';
  const returnTo = flowParam === 'register' ? getSafeInternalRedirectPath(searchParams.get('returnTo')) : null;

  if (!isVerifyFlow(flowParam) || !email) {
    return <Navigate to="/login" replace />;
  }

  if (flowParam === 'change' && !isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if ((flowParam === 'auth' || flowParam === 'login' || flowParam === 'register') && isAuthenticated) {
    return <Navigate to={flowParam === 'register' && returnTo ? returnTo : requiresProfileCompletion ? '/complete-profile' : '/account'} replace />;
  }

  return <VerifyEmailPageContent key={`${flowParam}:${email}:${returnTo ?? ''}`} flow={flowParam} email={email} returnTo={returnTo} />;
};

interface VerifyEmailPageContentProps {
  flow: VerifyFlow;
  email: string;
  returnTo: string | null;
}

const VerifyEmailPageContent = ({ flow, email, returnTo }: VerifyEmailPageContentProps) => {
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
  const [localMessage, setLocalMessage] = useState<string | null>(null);
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
        navigate(response.next_step === 'complete_profile' ? '/complete-profile' : '/account', { replace: true });
        return;
      }
      if (flow === 'login') {
        await verifyLoginCode(email, code);
        navigate('/account', { replace: true });
        return;
      }
      if (flow === 'register') {
        await verifyRegistrationCode(email, code);
        navigate(returnTo ?? '/account', { replace: true });
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
        const response = await requestEmailAuthCode(email);
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
      onBack={() => navigate(flow === 'change' ? '/account' : flow === 'reset' ? '/forgot-password' : '/login')}
    />
  );
};
