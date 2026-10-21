import {useState, type FormEvent} from 'react';
import {getProfile, requestContactEmailVerification, verifyContactEmailCode, type ProfileResponse} from '@/features/auth/api';
import {getAuthApiErrorMessage} from '../../shared/apiErrors';

interface UsePrimaryEmailVerificationOptions {
  profile: ProfileResponse;
  onProfileUpdate: (updated: ProfileResponse) => void;
  messages: {clear: () => void; setError: (message: string | null) => void; setSuccess: (message: string) => void};
}

/** Verifying the primary email with a code; success refreshes the profile's verified flag. */
export function usePrimaryEmailVerification({profile, onProfileUpdate, messages}: UsePrimaryEmailVerificationOptions) {
  const [primaryVerifying, setPrimaryVerifying] = useState(false);
  const [primaryVerifyCode, setPrimaryVerifyCode] = useState('');
  const [primaryVerifyLoading, setPrimaryVerifyLoading] = useState(false);
  const [primaryVerifyError, setPrimaryVerifyError] = useState<string | null>(null);
  const [primaryResendLoading, setPrimaryResendLoading] = useState(false);
  const primaryEmailId = profile.primary_email_id;

  const handlePrimaryToggleVerify = async () => {
    if (!primaryEmailId) return;
    messages.clear();
    setPrimaryVerifyError(null);
    setPrimaryVerifyCode('');
    setPrimaryResendLoading(true);
    try {
      await requestContactEmailVerification(primaryEmailId);
      setPrimaryVerifying(true);
      messages.setSuccess('Verification code sent to your primary email.');
    } catch (err) {
      messages.setError(getAuthApiErrorMessage(err));
    } finally {
      setPrimaryResendLoading(false);
    }
  };

  const handlePrimaryVerifySubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!primaryEmailId || primaryVerifyCode.length !== 6) return;
    setPrimaryVerifyLoading(true);
    setPrimaryVerifyError(null);
    messages.clear();
    try {
      await verifyContactEmailCode(primaryEmailId, primaryVerifyCode);
      setPrimaryVerifying(false);
      setPrimaryVerifyCode('');
      // Refresh profile to pick up the updated verified status
      onProfileUpdate(await getProfile());
      messages.setSuccess('Primary email verified successfully.');
    } catch (err) {
      setPrimaryVerifyError(getAuthApiErrorMessage(err));
    } finally {
      setPrimaryVerifyLoading(false);
    }
  };

  const handlePrimaryResend = async () => {
    if (!primaryEmailId) return;
    setPrimaryResendLoading(true);
    setPrimaryVerifyError(null);
    try {
      await requestContactEmailVerification(primaryEmailId);
      messages.setSuccess('Verification code resent.');
    } catch (err) {
      setPrimaryVerifyError(getAuthApiErrorMessage(err));
    } finally {
      setPrimaryResendLoading(false);
    }
  };

  const handlePrimaryCancelVerify = () => {
    setPrimaryVerifying(false);
    setPrimaryVerifyCode('');
    setPrimaryVerifyError(null);
  };

  return {
    primaryVerifying,
    primaryVerifyCode,
    setPrimaryVerifyCode,
    primaryVerifyLoading,
    primaryVerifyError,
    primaryResendLoading,
    handlePrimaryToggleVerify,
    handlePrimaryVerifySubmit,
    handlePrimaryResend,
    handlePrimaryCancelVerify,
  };
}
