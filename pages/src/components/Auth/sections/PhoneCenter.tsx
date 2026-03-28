import {useState, useEffect, type FormEvent} from 'react';
import {
    getContactPhones,
    createContactPhone,
    updateContactPhone,
    deleteContactPhone,
    type ContactPhone,
} from '../../../services/auth';
import {PhoneAddForm} from './PhoneAddForm';
import {PhoneCard} from './PhoneCard';
import {getAuthApiErrorMessage} from '../shared/apiErrors';
import {StatusAlert} from '../shared/StatusAlert';
import '../Auth.css';

export const PhoneCenter = () => {
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
        } catch (err) {
            setError(getAuthApiErrorMessage(err));
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
            setSuccessMessage('Phone number added.');
        } catch (err) {
            setAddError(getAuthApiErrorMessage(err));
        } finally {
            setAddLoading(false);
        }
    };

    const handleDelete = async (phoneId: string) => {
        if (!window.confirm('Are you sure you want to remove this phone number?')) return;
        clearMessages();
        try {
            await deleteContactPhone(phoneId);
            setPhones((prev) => prev.filter((p) => p.id !== phoneId));
            setSuccessMessage('Phone number removed.');
        } catch (err) {
            setError(getAuthApiErrorMessage(err));
        }
    };

    return (
        <div className="account-section">
            <h2 className="account-section-title">Phone Numbers</h2>

            {successMessage ? <StatusAlert tone="success" message={successMessage} style={{marginBottom: '1rem'}} /> : null}
            {error ? <StatusAlert tone="error" message={error} style={{marginBottom: '1rem'}} /> : null}

            {loading ? (
                <p style={{color: '#6b7280', fontSize: '0.875rem'}}>Loading phone numbers...</p>
            ) : (
                phones.map((phone) => (
                    <PhoneCard key={phone.id} phone={phone} onToggleSubscribe={handleSubscribeToggle} onDelete={handleDelete} />
                ))
            )}

            {!loading && phones.length === 0 && !showAddForm && (
                <p style={{color: '#6b7280', fontSize: '0.875rem', marginTop: '0.5rem'}}>
                    No phone numbers added yet.
                </p>
            )}

            {showAddForm ? (
                <PhoneAddForm
                    addRegion={addRegion}
                    addPhoneNumber={addPhoneNumber}
                    addSubscribe={addSubscribe}
                    addLoading={addLoading}
                    addError={addError}
                    onRegionChange={setAddRegion}
                    onPhoneNumberChange={setAddPhoneNumber}
                    onSubscribeChange={setAddSubscribe}
                    onSubmit={handleAddSubmit}
                    onCancel={() => {
                        setShowAddForm(false);
                        setAddError(null);
                    }}
                />
            ) : (
                <button
                    type="button"
                    className="auth-form-submit"
                    onClick={() => {
                        setShowAddForm(true);
                        clearMessages();
                    }}
                    style={{marginTop: '0.75rem'}}
                >
                    Add Phone
                </button>
            )}
        </div>
    );
};
