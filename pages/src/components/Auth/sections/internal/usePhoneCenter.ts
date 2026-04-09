import {useState, useEffect, type FormEvent} from 'react';
import {
    getContactPhones,
    createContactPhone,
    updateContactPhone,
    deleteContactPhone,
    requestContactPhoneVerification,
    verifyContactPhoneCode,
    type ContactPhone,
} from '../../../../services/auth';
import {USER_FACING_GENERIC_ERROR_ZH} from '../../shared/apiErrors';

export const usePhoneCenter = () => {
    const [phones, setPhones] = useState<ContactPhone[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);

    // Add form state
    const [showAddForm, setShowAddForm] = useState(false);
    const [addPhoneNumber, setAddPhoneNumber] = useState('');
    const [addRegion, setAddRegion] = useState('1-US');
    const [addSubscribe, setAddSubscribe] = useState(false);
    const [addLoading, setAddLoading] = useState(false);
    const [addError, setAddError] = useState<string | null>(null);

    // Verification state
    const [verifyingId, setVerifyingId] = useState<string | null>(null);
    const [verifyCode, setVerifyCode] = useState('');
    const [verifyLoading, setVerifyLoading] = useState(false);
    const [verifyError, setVerifyError] = useState<string | null>(null);
    const [resendLoading, setResendLoading] = useState(false);

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

    const handleSubscribeToggle = async (phone: ContactPhone) => {
        clearMessages();
        try {
            const updated = await updateContactPhone(phone.id, {subscribe: !phone.subscribe});
            setPhones((prev) => prev.map((p) => (p.id === phone.id ? updated : p)));
        } catch {
            setError(USER_FACING_GENERIC_ERROR_ZH);
        }
    };

    const handleAddSubmit = async (e: FormEvent) => {
        e.preventDefault();
        setAddLoading(true);
        setAddError(null);
        clearMessages();
        try {
            const created = await createContactPhone({
                phone_number: addPhoneNumber.trim(),
                region: addRegion,
                subscribe: addSubscribe,
            });
            setPhones((prev) => [created, ...prev]);
            setAddPhoneNumber('');
            setAddRegion('1-US');
            setAddSubscribe(false);
            setShowAddForm(false);

            // Auto-trigger verification for the newly created phone
            try {
                await requestContactPhoneVerification(created.id);
                setVerifyingId(created.id);
                setVerifyCode('');
                setSuccessMessage('Phone number added. Please enter the verification code sent via SMS.');
            } catch {
                setSuccessMessage('Phone number added. Click "Verify" to receive a verification code.');
            }
        } catch {
            setAddError(USER_FACING_GENERIC_ERROR_ZH);
        } finally {
            setAddLoading(false);
        }
    };

    const handleToggleVerify = async (phoneId: string) => {
        clearMessages();
        setVerifyError(null);
        setVerifyCode('');
        setResendLoading(true);
        try {
            await requestContactPhoneVerification(phoneId);
            setVerifyingId(phoneId);
            setSuccessMessage('Verification code sent via SMS.');
        } catch {
            setError(USER_FACING_GENERIC_ERROR_ZH);
        } finally {
            setResendLoading(false);
        }
    };

    const handleVerifySubmit = async (event: FormEvent) => {
        event.preventDefault();
        if (!verifyingId || verifyCode.length !== 6) return;
        setVerifyLoading(true);
        setVerifyError(null);
        clearMessages();
        try {
            const updated = await verifyContactPhoneCode(verifyingId, verifyCode);
            setPhones((prev) => prev.map((p) => (p.id === verifyingId ? updated : p)));
            setVerifyingId(null);
            setVerifyCode('');
            setSuccessMessage('Phone number verified successfully.');
        } catch {
            setVerifyError(USER_FACING_GENERIC_ERROR_ZH);
        } finally {
            setVerifyLoading(false);
        }
    };

    const handleResend = async (phoneId: string) => {
        setResendLoading(true);
        setVerifyError(null);
        try {
            await requestContactPhoneVerification(phoneId);
            setSuccessMessage('Verification code resent.');
        } catch {
            setVerifyError(USER_FACING_GENERIC_ERROR_ZH);
        } finally {
            setResendLoading(false);
        }
    };

    const handleCancelVerify = () => {
        setVerifyingId(null);
        setVerifyCode('');
        setVerifyError(null);
    };

    const handleDelete = async (phoneId: string) => {
        if (!window.confirm('Are you sure you want to remove this phone number?')) return;
        clearMessages();
        try {
            await deleteContactPhone(phoneId);
            setPhones((prev) => prev.filter((p) => p.id !== phoneId));
            if (verifyingId === phoneId) {
                setVerifyingId(null);
                setVerifyCode('');
            }
            setSuccessMessage('Phone number removed.');
        } catch {
            setError(USER_FACING_GENERIC_ERROR_ZH);
        }
    };

    return {
        phones,
        loading,
        error,
        successMessage,
        showAddForm,
        setShowAddForm,
        addPhoneNumber,
        setAddPhoneNumber,
        addRegion,
        setAddRegion,
        addSubscribe,
        setAddSubscribe,
        addLoading,
        addError,
        setAddError,
        verifyingId,
        verifyCode,
        setVerifyCode,
        verifyLoading,
        verifyError,
        resendLoading,
        clearMessages,
        handleSubscribeToggle,
        handleAddSubmit,
        handleToggleVerify,
        handleVerifySubmit,
        handleResend,
        handleCancelVerify,
        handleDelete,
    };
};
