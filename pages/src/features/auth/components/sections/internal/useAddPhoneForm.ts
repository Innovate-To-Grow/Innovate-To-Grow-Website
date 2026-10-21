import {useState, type Dispatch, type FormEvent, type SetStateAction} from 'react';
import {
    createContactPhone,
    deleteContactPhone,
    requestContactPhoneVerification,
    updateContactPhone,
    verifyContactPhoneCode,
    type ContactPhone,
} from '@/features/auth/api';
import {USER_FACING_GENERIC_ERROR} from '../../shared/apiErrors';
import {canSubmitNationalPhone} from '@/lib/format/phoneInput';
import type {useContactCodeVerification} from './useContactCodeVerification';

export const TERMS_REQUIRED = 'Please accept the Privacy/Legal Notice and Privacy Statement to continue.';

type PhoneVerification = ReturnType<typeof useContactCodeVerification<ContactPhone>>;

interface CenterMessages {
    clear: () => void;
    setError: (message: string | null) => void;
    setSuccess: (message: string) => void;
}

/** The add-a-number form, and the new number while its SMS code is pending. */
export const useAddPhoneForm = () => {
    const [showAddForm, setShowAddForm] = useState(false);
    const [addPhoneNumber, setAddPhoneNumber] = useState('');
    const [addSubscribe, setAddSubscribe] = useState(false);
    const [addTermsAccepted, setAddTermsAccepted] = useState(false);
    const [addLoading, setAddLoading] = useState(false);
    const [addError, setAddError] = useState<string | null>(null);
    /** Created on server but not yet shown in the list until SMS verification succeeds. */
    const [pendingNewPhone, setPendingNewPhone] = useState<ContactPhone | null>(null);
    const [abandonPendingLoading, setAbandonPendingLoading] = useState(false);

    const resetPendingAdd = () => {
        setAddSubscribe(false);
        setAddTermsAccepted(false);
    };

    return {
        showAddForm,
        setShowAddForm,
        addPhoneNumber,
        setAddPhoneNumber,
        addSubscribe,
        setAddSubscribe,
        addTermsAccepted,
        setAddTermsAccepted,
        addLoading,
        setAddLoading,
        addError,
        setAddError,
        pendingNewPhone,
        setPendingNewPhone,
        abandonPendingLoading,
        setAbandonPendingLoading,
        resetPendingAdd,
    };
};

type AddPhoneForm = ReturnType<typeof useAddPhoneForm>;

/** Code verification for the account's numbers, where a pending new number joins the list once verified. */
export const phoneVerificationOptions = (
    form: AddPhoneForm,
    setPhones: Dispatch<SetStateAction<ContactPhone[]>>,
    messages: CenterMessages,
) => ({
    requestCode: requestContactPhoneVerification,
    verifyCode: verifyContactPhoneCode,
    // The pending new number joins the list only now; an existing one is replaced in place.
    onVerified: (updated: ContactPhone, phoneId: string) => {
        const wasPendingAdd = form.pendingNewPhone?.id === phoneId;
        setPhones((prev) => (wasPendingAdd ? [updated, ...prev] : prev.map((p) => (p.id === phoneId ? updated : p))));
        if (wasPendingAdd) {
            form.setPendingNewPhone(null);
            form.setShowAddForm(false);
            form.resetPendingAdd();
        }
    },
    verifiedMessage: 'Phone number verified successfully.',
    errorMessage: () => USER_FACING_GENERIC_ERROR,
    messages,
    blockSubmit: (phoneId: string) =>
        form.pendingNewPhone?.id === phoneId && !form.addTermsAccepted ? TERMS_REQUIRED : null,
    // The subscribe choice can change while the new number's code is pending.
    beforeVerify: async (phoneId: string) => {
        const pending = form.pendingNewPhone;
        if (pending?.id === phoneId && pending.subscribe !== form.addSubscribe) {
            await updateContactPhone(phoneId, {subscribe: form.addSubscribe});
        }
    },
    // The pending number's form already says a code was sent.
    resendMessage: (phoneId: string) =>
        form.pendingNewPhone?.id !== phoneId ? 'New code sent. Enter it below and tap Submit code.' : null,
});

/** Starting, submitting, resending and abandoning the add-a-number flow. */
export const useAddPhoneActions = (form: AddPhoneForm, verification: PhoneVerification, messages: CenterMessages) => {
    const beginAddPhoneFlow = () => {
        messages.clear();
        form.setShowAddForm(true);
        form.setPendingNewPhone(null);
        verification.cancel();
        form.setAddPhoneNumber('');
        form.setAddSubscribe(false);
        form.setAddTermsAccepted(false);
        form.setAddError(null);
    };

    const handleAddSubmit = async (e: FormEvent) => {
        e.preventDefault();
        if (!form.addTermsAccepted) {
            form.setAddError(TERMS_REQUIRED);
            return;
        }
        if (!canSubmitNationalPhone(form.addPhoneNumber)) {
            form.setAddError('Enter a 10-digit US phone number.');
            return;
        }
        form.setAddLoading(true);
        form.setAddError(null);
        messages.clear();
        try {
            const created = await createContactPhone({
                phone_number: form.addPhoneNumber,
                region: '1-US',
                subscribe: form.addSubscribe,
            });
            form.setAddPhoneNumber('');
            form.setPendingNewPhone(created);
            verification.begin(created.id);
            verification.setVerifyError(null);

            try {
                await requestContactPhoneVerification(created.id);
            } catch {
                messages.setError('SMS could not be sent. Tap Resend Code.');
            }
        } catch {
            form.setAddError(USER_FACING_GENERIC_ERROR);
        } finally {
            form.setAddLoading(false);
        }
    };

    const handleResendPendingPhone = () => {
        if (form.pendingNewPhone) void verification.resend(form.pendingNewPhone.id);
    };

    const handleAbandonPendingPhone = async () => {
        const pending = form.pendingNewPhone;
        if (!pending) return;
        if (!window.confirm('Discard this number? It will be removed until you add it again.')) return;
        form.setAbandonPendingLoading(true);
        messages.setError(null);
        try {
            await deleteContactPhone(pending.id);
            form.setPendingNewPhone(null);
            verification.cancel();
            form.resetPendingAdd();
        } catch {
            messages.setError(USER_FACING_GENERIC_ERROR);
        } finally {
            form.setAbandonPendingLoading(false);
        }
    };

    return {beginAddPhoneFlow, handleAddSubmit, handleResendPendingPhone, handleAbandonPendingPhone};
};
