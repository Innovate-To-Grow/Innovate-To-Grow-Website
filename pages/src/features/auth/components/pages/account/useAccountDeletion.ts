import {useCallback, useState, type FormEvent} from 'react';
import {useNavigate} from 'react-router';
import {confirmAccountDeletion, requestAccountDeletionCode, verifyAccountDeletionCode} from '@/features/auth/api';
import {getAuthApiErrorMessage} from '../../shared/apiErrors';

/** Deleting the account: request a code, verify it for a one-time token, confirm; then sign out. */
export function useAccountDeletion(logout: () => void) {
  const navigate = useNavigate();
  const [deleteCodeRequested, setDeleteCodeRequested] = useState(false);
  const [deleteCode, setDeleteCode] = useState('');
  const [deleteVerificationToken, setDeleteVerificationToken] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const clearDeleteFeedback = useCallback(() => {
    setDeleteMessage(null);
    setDeleteError(null);
  }, []);

  const resetDeleteForm = useCallback(() => {
    setDeleteCodeRequested(false);
    setDeleteCode('');
    setDeleteVerificationToken(null);
  }, []);

  const handleDeleteRequestCode = async () => {
    setDeleteLoading(true);
    clearDeleteFeedback();
    setDeleteVerificationToken(null);

    try {
      const response = await requestAccountDeletionCode();
      setDeleteCodeRequested(true);
      setDeleteCode('');
      setDeleteMessage(response.message || 'Deletion verification code sent.');
    } catch (err: unknown) {
      setDeleteError(getAuthApiErrorMessage(err));
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleDeleteVerifyCode = async (event: FormEvent) => {
    event.preventDefault();
    setDeleteLoading(true);
    clearDeleteFeedback();

    try {
      const response = await verifyAccountDeletionCode(deleteCode);
      setDeleteVerificationToken(response.verification_token);
      setDeleteMessage(response.message || 'Deletion code verified.');
    } catch (err: unknown) {
      setDeleteError(getAuthApiErrorMessage(err));
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleDeleteConfirm = async (event: FormEvent) => {
    event.preventDefault();
    if (!deleteVerificationToken) {
      setDeleteError('Verify your deletion code before deleting your account.');
      return;
    }

    setDeleteLoading(true);
    clearDeleteFeedback();

    try {
      const response = await confirmAccountDeletion(deleteVerificationToken);
      resetDeleteForm();
      setDeleteMessage(response.message || 'Account deleted successfully.');
      logout();
      navigate('/login', {replace: true});
    } catch (err: unknown) {
      setDeleteError(getAuthApiErrorMessage(err));
    } finally {
      setDeleteLoading(false);
    }
  };

  return {
    deleteCodeRequested,
    deleteCode,
    deleteVerificationToken,
    deleteLoading,
    deleteMessage,
    deleteError,
    setDeleteCode,
    handleDeleteRequestCode,
    handleDeleteVerifyCode,
    handleDeleteConfirm,
  };
}
