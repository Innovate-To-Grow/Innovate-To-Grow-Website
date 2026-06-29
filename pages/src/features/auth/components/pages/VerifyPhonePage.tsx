import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { getPostAuthPath, getSafeInternalRedirectPath } from '@/features/auth/api/redirects';
import { useAuth } from '../AuthContext';
import { VerifyEmailView } from './verify/VerifyEmailView';
import {
  canSubmitNationalPhone,
  formatNationalInputDisplay,
  parsePhoneInputToNationalDigits,
} from '../sections/internal/phoneInput';

export const VerifyPhonePage = () => {
  const { isAuthenticated, requiresProfileCompletion } = useAuth();
  const [searchParams] = useSearchParams();

  const phone = parsePhoneInputToNationalDigits(searchParams.get('phone') ?? '');
  const returnTo = getSafeInternalRedirectPath(searchParams.get('returnTo'));

  if (!canSubmitNationalPhone(phone)) {
    return <Navigate to="/login" replace />;
  }

  if (isAuthenticated) {
    return <Navigate to={returnTo ?? (requiresProfileCompletion ? '/complete-profile' : '/account')} replace />;
  }

  return <VerifyPhonePageContent key={`${phone}:${returnTo ?? ''}`} phone={phone} returnTo={returnTo} />;
};

interface VerifyPhonePageContentProps {
  phone: string;
  returnTo: string | null;
}

const VerifyPhonePageContent = ({ phone, returnTo }: VerifyPhonePageContentProps) => {
  const { error, isLoading, verifyPhoneAuthCode, requestPhoneAuthCode, clearError } = useAuth();
  const navigate = useNavigate();

  const [code, setCode] = useState('');
  const [localMessage, setLocalMessage] = useState<string | null>(null);

  useEffect(() => {
    clearError();
  }, [clearError]);

  const handleVerify = async (event: FormEvent) => {
    event.preventDefault();
    setLocalMessage(null);
    try {
      const response = await verifyPhoneAuthCode(phone, code);
      navigate(getPostAuthPath(response, returnTo), { replace: true });
    } catch {
      // handled by context
    }
  };

  const handleResend = async () => {
    setLocalMessage(null);
    try {
      const response = await requestPhoneAuthCode(phone, '1-US', 'login');
      setLocalMessage(response.message);
    } catch {
      // handled by context
    }
  };

  return (
    <VerifyEmailView
      flow="login"
      email={formatNationalInputDisplay(phone)}
      title="Verify Your Phone"
      subtitle="Enter the 6-digit code we texted you to finish signing in or set up your account."
      buttonLabel="Verify"
      code={code}
      verificationToken={null}
      newPassword=""
      confirmPassword=""
      localMessage={localMessage}
      localSuccess={null}
      error={error}
      isLoading={isLoading}
      onCodeChange={(value) => {
        setCode(value);
        clearError();
      }}
      onNewPasswordChange={() => {}}
      onConfirmPasswordChange={() => {}}
      onVerifySubmit={handleVerify}
      onPasswordSubmit={(event) => event.preventDefault()}
      onResend={handleResend}
      onBack={() => navigate('/login')}
    />
  );
};
