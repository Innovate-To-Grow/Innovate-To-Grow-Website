import {useState, useEffect} from 'react';
import {
  getContactPhones,
  updateContactPhone,
  deleteContactPhone,
  type ContactPhone,
} from '@/features/auth/api';
import {USER_FACING_GENERIC_ERROR} from '../../shared/apiErrors';
import {phoneVerificationOptions, useAddPhoneActions, useAddPhoneForm} from './useAddPhoneForm';
import {useContactCodeVerification} from './useContactCodeVerification';

/**
 * The account's phone numbers. A new number is created on the server but stays out of the list (as
 * `pendingNewPhone`) until its SMS code is verified; abandoning it deletes it again.
 */
export const usePhoneCenter = () => {
    const [phones, setPhones] = useState<ContactPhone[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);
    const form = useAddPhoneForm();

    useEffect(() => {
        const fetchPhones = async () => {
            try {
                const data = await getContactPhones();
                setPhones(data);
            } catch (err) {
                console.error('[PhoneCenter] Failed to load contact phones:', err);
            } finally {
                setLoading(false);
            }
        };
        fetchPhones();
    }, []);

    const clearMessages = () => {
        setError(null);
        setSuccessMessage(null);
    };
    const messages = {clear: clearMessages, setError, setSuccess: setSuccessMessage};
    const verification = useContactCodeVerification(phoneVerificationOptions(form, setPhones, messages));
    const addActions = useAddPhoneActions(form, verification, messages);

    const handleSubscribeToggle = async (phone: ContactPhone) => {
        clearMessages();
        try {
            const updated = await updateContactPhone(phone.id, {subscribe: !phone.subscribe});
            setPhones((prev) => prev.map((p) => (p.id === phone.id ? updated : p)));
        } catch {
            setError(USER_FACING_GENERIC_ERROR);
        }
    };

    const handleDelete = async (phoneId: string) => {
        if (!window.confirm('Are you sure you want to remove this phone number?')) return;
        clearMessages();
        try {
            await deleteContactPhone(phoneId);
            setPhones((prev) => prev.filter((p) => p.id !== phoneId));
            verification.forget(phoneId);
            setSuccessMessage('Phone number removed.');
        } catch {
            setError(USER_FACING_GENERIC_ERROR);
        }
    };

    return {
        phones,
        loading,
        error,
        successMessage,
        showAddForm: form.showAddForm,
        setShowAddForm: form.setShowAddForm,
        pendingNewPhone: form.pendingNewPhone,
        addPhoneNumber: form.addPhoneNumber,
        setAddPhoneNumber: form.setAddPhoneNumber,
        addSubscribe: form.addSubscribe,
        setAddSubscribe: form.setAddSubscribe,
        addTermsAccepted: form.addTermsAccepted,
        setAddTermsAccepted: form.setAddTermsAccepted,
        addLoading: form.addLoading,
        addError: form.addError,
        setAddError: form.setAddError,
        verifyingId: verification.verifyingId,
        verifyCode: verification.verifyCode,
        setVerifyCode: verification.setVerifyCode,
        verifyLoading: verification.verifyLoading,
        verifyError: verification.verifyError,
        resendLoading: verification.resendLoading,
        abandonPendingLoading: form.abandonPendingLoading,
        clearMessages,
        ...addActions,
        handleSubscribeToggle,
        handleToggleVerify: verification.requestVerification,
        handleVerifySubmit: verification.submit,
        handleResend: verification.resend,
        handleCancelVerify: verification.cancel,
        handleDelete,
    };
};
