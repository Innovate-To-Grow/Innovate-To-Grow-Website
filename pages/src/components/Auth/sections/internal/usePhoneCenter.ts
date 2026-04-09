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
import {canSubmitNationalPhone, capNationalDigitsForRegion} from './phoneInput';

export const usePhoneCenter = () => {
    const [phones, setPhones] = useState<ContactPhone[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);

    // Add form state
    const [showAddForm, setShowAddForm] = useState(false);
    const [addPhoneNumber, setAddPhoneNumber] = useState('');
    const [addRegion, setAddRegion] = useState('1-US');
    const [addSubscribe, setAddSubscribe] = useState(true);
    const [addLoading, setAddLoading] = useState(false);
    const [addError, setAddError] = useState<string | null>(null);
    /** Created on server but not yet shown in the list until SMS verification succeeds. */
    const [pendingNewPhone, setPendingNewPhone] = useState<ContactPhone | null>(null);
    const [abandonPendingLoading, setAbandonPendingLoading] = useState(false);

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

    const beginAddPhoneFlow = () => {
        clearMessages();
        setShowAddForm(true);
        setPendingNewPhone(null);
        setVerifyingId(null);
        setVerifyCode('');
        setVerifyError(null);
        setAddPhoneNumber('');
        setAddRegion('1-US');
        setAddSubscribe(true);
        setAddError(null);
    };

    const handleAddRegionChange = (region: string) => {
        setAddRegion(region);
        setAddPhoneNumber((prev) => capNationalDigitsForRegion(prev, region));
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
        if (!canSubmitNationalPhone(addPhoneNumber, addRegion)) return;
        setAddLoading(true);
        setAddError(null);
        clearMessages();
        try {
            const created = await createContactPhone({
                phone_number: addPhoneNumber,
                region: addRegion,
                subscribe: addSubscribe,
            });
            setAddPhoneNumber('');
            setAddRegion('1-US');
            setAddSubscribe(true);
            setPendingNewPhone(created);
            setVerifyingId(created.id);
            setVerifyCode('');
            setVerifyError(null);

            try {
                await requestContactPhoneVerification(created.id);
            } catch {
                setError('SMS could not be sent. Tap Resend Code.');
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
            setSuccessMessage('Code sent. Enter it below and tap Submit code.');
        } catch {
            setError(USER_FACING_GENERIC_ERROR_ZH);
        } finally {
            setResendLoading(false);
        }
    };

    const handleVerifySubmit = async (event: FormEvent) => {
        event.preventDefault();
        if (!verifyingId || verifyCode.length !== 6) return;
        const targetId = verifyingId;
        const wasPendingAdd = pendingNewPhone?.id === targetId;
        setVerifyLoading(true);
        setVerifyError(null);
        clearMessages();
        try {
            const updated = await verifyContactPhoneCode(targetId, verifyCode);
            setPhones((prev) => (wasPendingAdd ? [updated, ...prev] : prev.map((p) => (p.id === targetId ? updated : p))));
            setVerifyingId(null);
            setVerifyCode('');
            if (wasPendingAdd) {
                setPendingNewPhone(null);
                setShowAddForm(false);
            }
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
            if (pendingNewPhone?.id !== phoneId) {
                setSuccessMessage('New code sent. Enter it below and tap Submit code.');
            }
        } catch {
            setVerifyError(USER_FACING_GENERIC_ERROR_ZH);
        } finally {
            setResendLoading(false);
        }
    };

    const handleResendPendingPhone = () => {
        if (pendingNewPhone) void handleResend(pendingNewPhone.id);
    };

    const handleCancelVerify = () => {
        setVerifyingId(null);
        setVerifyCode('');
        setVerifyError(null);
    };

    const handleAbandonPendingPhone = async () => {
        if (!pendingNewPhone) return;
        if (!window.confirm('Discard this number? It will be removed until you add it again.')) return;
        setAbandonPendingLoading(true);
        setError(null);
        try {
            await deleteContactPhone(pendingNewPhone.id);
            setPendingNewPhone(null);
            setVerifyingId(null);
            setVerifyCode('');
            setVerifyError(null);
        } catch {
            setError(USER_FACING_GENERIC_ERROR_ZH);
        } finally {
            setAbandonPendingLoading(false);
        }
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
        pendingNewPhone,
        addPhoneNumber,
        setAddPhoneNumber,
        addRegion,
        setAddRegion,
        handleAddRegionChange,
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
        abandonPendingLoading,
        clearMessages,
        beginAddPhoneFlow,
        handleSubscribeToggle,
        handleAddSubmit,
        handleToggleVerify,
        handleVerifySubmit,
        handleResend,
        handleResendPendingPhone,
        handleCancelVerify,
        handleAbandonPendingPhone,
        handleDelete,
    };
};
