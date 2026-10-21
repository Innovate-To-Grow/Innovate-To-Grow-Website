import {useCallback, useState, type FormEvent} from 'react';
import {confirmPasswordChange, requestPasswordChangeCode, verifyPasswordChangeCode} from '@/features/auth/api';
import {getAuthApiErrorMessage} from '../../shared/apiErrors';

/**
 * Changing the password: request a code (emailed, or texted to a phone-only account), verify it for a
 * one-time token, then set the new password with that token.
 */
export function usePasswordChange(getPasswordEmail: () => string | undefined) {
  const [passwordCodeRequested, setPasswordCodeRequested] = useState(false);
  const [passwordCode, setPasswordCode] = useState('');
  const [passwordVerificationToken, setPasswordVerificationToken] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordChannel, setPasswordChannel] = useState<'email' | 'sms' | null>(null);

  const clearPasswordFeedback = useCallback(() => {
    setPasswordMessage(null);
    setPasswordError(null);
  }, []);

  const resetPasswordForm = useCallback(() => {
    setPasswordCodeRequested(false);
    setPasswordCode('');
    setPasswordVerificationToken(null);
    setNewPassword('');
    setConfirmPassword('');
    setPasswordChannel(null);
  }, []);

  const handlePasswordRequestCode = async () => {
    setPasswordLoading(true);
    clearPasswordFeedback();
    setPasswordVerificationToken(null);
    setNewPassword('');
    setConfirmPassword('');

    try {
      const response = await requestPasswordChangeCode(getPasswordEmail());
      setPasswordCodeRequested(true);
      setPasswordCode('');
      setPasswordChannel(response.channel ?? null);
      const sentTo = response.destination ? ` to ${response.destination}` : '';
      const channelLabel = response.channel === 'sms' ? 'texted a code' : 'emailed a code';
      setPasswordMessage(response.message || `We ${channelLabel}${sentTo}.`);
    } catch (err: unknown) {
      setPasswordError(getAuthApiErrorMessage(err));
    } finally {
      setPasswordLoading(false);
    }
  };

  const handlePasswordVerifyCode = async (event: FormEvent) => {
    event.preventDefault();
    setPasswordLoading(true);
    clearPasswordFeedback();

    try {
      const response = await verifyPasswordChangeCode(passwordCode, getPasswordEmail());
      setPasswordVerificationToken(response.verification_token);
      setPasswordMessage(response.message || 'Code verified. You can now enter a new password.');
    } catch (err: unknown) {
      setPasswordError(getAuthApiErrorMessage(err));
    } finally {
      setPasswordLoading(false);
    }
  };

  const handlePasswordConfirm = async (event: FormEvent) => {
    event.preventDefault();
    if (!passwordVerificationToken) {
      setPasswordError('Verify your code before changing your password.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match.');
      return;
    }

    setPasswordLoading(true);
    clearPasswordFeedback();

    try {
      const response = await confirmPasswordChange(passwordVerificationToken, newPassword, confirmPassword);
      resetPasswordForm();
      setPasswordMessage(response.message || 'Password changed successfully.');
    } catch (err: unknown) {
      setPasswordError(getAuthApiErrorMessage(err));
    } finally {
      setPasswordLoading(false);
    }
  };

  return {
    passwordCodeRequested,
    passwordCode,
    passwordVerificationToken,
    newPassword,
    confirmPassword,
    passwordLoading,
    passwordMessage,
    passwordError,
    passwordChannel,
    setPasswordCode,
    setNewPassword,
    setConfirmPassword,
    handlePasswordConfirm,
    handlePasswordRequestCode,
    handlePasswordVerifyCode,
  };
}
