import {useState, useEffect, type FormEvent} from 'react';
import {
    getContactPhones,
    createContactPhone,
    updateContactPhone,
    deleteContactPhone,
    type ContactPhone,
} from '../../../services/auth';
import {PHONE_REGION_CHOICES} from '../../../constants/phoneRegions';
import '../Auth.css';

function getErrorMessage(err: unknown): string {
    if (typeof err === 'object' && err !== null) {
        const axiosError = err as { response?: { data?: Record<string, unknown> } };
        if (axiosError.response?.data) {
            const data = axiosError.response.data;
            const firstKey = Object.keys(data)[0];
            if (firstKey) {
                const value = data[firstKey];
                if (Array.isArray(value)) return value[0] as string;
                if (typeof value === 'string') return value;
            }
        }
    }
    return 'An unexpected error occurred. Please try again.';
}

function getDialCode(regionCode: string): string {
    const numeric = regionCode.split('-')[0];
    return `+${numeric}`;
}

function formatPhoneDisplay(phoneNumber: string, region: string): string {
    const countryCode = region.split('-')[0];
    const prefix = `+${countryCode}`;

    // Strip the country-code prefix to get the national number
    let national = phoneNumber;
    if (phoneNumber.startsWith(prefix)) {
        national = phoneNumber.slice(prefix.length);
    } else if (phoneNumber.startsWith('+')) {
        return `${prefix} ${phoneNumber.slice(prefix.length)}`;
    }

    // US / Canada
    if (countryCode === '1') {
        if (national.length === 10) {
            return `+1 (${national.slice(0, 3)}) ${national.slice(3, 6)}-${national.slice(6)}`;
        }
        if (national.length === 7) {
            return `+1 ${national.slice(0, 3)}-${national.slice(3)}`;
        }
        // Other lengths: +1 XXX XXX ...
        return `+1 ${national.replace(/(\d{3})(?=\d)/g, '$1 ').trim()}`;
    }

    // China / HK / Macau / Taiwan
    if (countryCode === '86' && national.length === 11) {
        return `+86 ${national.slice(0, 3)} ${national.slice(3, 7)} ${national.slice(7)}`;
    }
    if (countryCode === '852' && national.length === 8) {
        return `+852 ${national.slice(0, 4)} ${national.slice(4)}`;
    }
    if (countryCode === '853' && national.length === 8) {
        return `+853 ${national.slice(0, 4)} ${national.slice(4)}`;
    }
    if (countryCode === '886' && national.length === 9) {
        return `+886 ${national.slice(0, 1)} ${national.slice(1, 5)} ${national.slice(5)}`;
    }

    // Japan: +81 X-XXXX-XXXX or +81 XX-XXXX-XXXX
    if (countryCode === '81' && national.length === 10) {
        return `+81 ${national.slice(0, 2)} ${national.slice(2, 6)} ${national.slice(6)}`;
    }

    // South Korea: +82 XX-XXXX-XXXX
    if (countryCode === '82' && national.length === 10) {
        return `+82 ${national.slice(0, 2)} ${national.slice(2, 6)} ${national.slice(6)}`;
    }

    // UK: +44 XXXX XXXXXX
    if (countryCode === '44' && national.length === 10) {
        return `+44 ${national.slice(0, 4)} ${national.slice(4)}`;
    }

    // India: +91 XXXXX XXXXX
    if (countryCode === '91' && national.length === 10) {
        return `+91 ${national.slice(0, 5)} ${national.slice(5)}`;
    }

    // Australia: +61 XXX XXX XXX
    if (countryCode === '61' && national.length === 9) {
        return `+61 ${national.slice(0, 3)} ${national.slice(3, 6)} ${national.slice(6)}`;
    }

    // Germany: +49 XXXX XXXXXXX
    if (countryCode === '49' && (national.length === 10 || national.length === 11)) {
        return `+49 ${national.slice(0, 4)} ${national.slice(4)}`;
    }

    // France: +33 X XX XX XX XX
    if (countryCode === '33' && national.length === 9) {
        return `+33 ${national.slice(0, 1)} ${national.slice(1, 3)} ${national.slice(3, 5)} ${national.slice(5, 7)} ${national.slice(7)}`;
    }

    // Brazil: +55 XX XXXXX-XXXX
    if (countryCode === '55' && national.length === 11) {
        return `+55 ${national.slice(0, 2)} ${national.slice(2, 7)}-${national.slice(7)}`;
    }

    // Mexico: +52 XX XXXX XXXX
    if (countryCode === '52' && national.length === 10) {
        return `+52 ${national.slice(0, 2)} ${national.slice(2, 6)} ${national.slice(6)}`;
    }

    // Default: +CC then digits in groups of 4
    const groups: string[] = [];
    for (let i = 0; i < national.length; i += 4) {
        groups.push(national.slice(i, i + 4));
    }
    return `${prefix} ${groups.join(' ')}`;
}

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
            setError(getErrorMessage(err));
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
            setAddError(getErrorMessage(err));
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
            setError(getErrorMessage(err));
        }
    };

    return (
        <div className="account-section">
            <h2 className="account-section-title">Phone Numbers</h2>

            {successMessage && (
                <div className="auth-alert success" style={{marginBottom: '1rem'}}>
                    <i className="fa fa-check-circle auth-alert-icon"/>
                    <span>{successMessage}</span>
                </div>
            )}

            {error && (
                <div className="auth-alert error" style={{marginBottom: '1rem'}}>
                    <i className="fa fa-exclamation-circle auth-alert-icon"/>
                    <span>{error}</span>
                </div>
            )}

            {loading ? (
                <p style={{color: '#6b7280', fontSize: '0.875rem'}}>Loading phone numbers...</p>
            ) : (
                phones.map((phone) => (
                    <div key={phone.id} className="email-center-card">
                        <div className="email-center-row">
                            <div style={{flex: 1, minWidth: 0}}>
                                <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap'}}>
                                    <span style={{fontWeight: 500, color: '#1f2937'}}>
                                        {formatPhoneDisplay(phone.phone_number, phone.region)}
                                    </span>
                                    <span className="email-center-badge primary">
                                        {phone.region_display}
                                    </span>
                                </div>
                                <div className="email-center-actions">
                                    <label className="email-center-toggle" aria-label="Receive notifications">
                                        <input
                                            type="checkbox"
                                            checked={phone.subscribe}
                                            onChange={() => handleSubscribeToggle(phone)}
                                        />
                                        <span className="email-center-toggle-slider"/>
                                        <span className="email-center-toggle-label">Notifications</span>
                                    </label>
                                    <button
                                        type="button"
                                        className="email-center-btn delete"
                                        onClick={() => handleDelete(phone.id)}
                                    >
                                        Remove
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                ))
            )}

            {!loading && phones.length === 0 && !showAddForm && (
                <p style={{color: '#6b7280', fontSize: '0.875rem', marginTop: '0.5rem'}}>
                    No phone numbers added yet.
                </p>
            )}

            {showAddForm ? (
                <div className="email-center-add-form">
                    <h3 className="account-subsection-title">Add Phone Number</h3>
                    {addError && (
                        <div className="auth-alert error" style={{marginBottom: '0.75rem'}}>
                            <i className="fa fa-exclamation-circle auth-alert-icon"/>
                            <span>{addError}</span>
                        </div>
                    )}
                    <form onSubmit={handleAddSubmit} className="email-center-add-fields">
                        <div className="auth-form-group">
                            <label className="auth-form-label" htmlFor="add-phone-region">
                                Region
                            </label>
                            <select
                                id="add-phone-region"
                                className="auth-form-input auth-form-select"
                                value={addRegion}
                                onChange={(e) => setAddRegion(e.target.value)}
                                disabled={addLoading}
                            >
                                {PHONE_REGION_CHOICES.map((r) => (
                                    <option key={r.code} value={r.code}>
                                        {r.label} ({getDialCode(r.code)})
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div className="auth-form-group">
                            <label className="auth-form-label" htmlFor="add-phone-number">
                                Phone Number
                            </label>
                            <input
                                id="add-phone-number"
                                type="tel"
                                className="auth-form-input"
                                value={addPhoneNumber}
                                onChange={(e) => setAddPhoneNumber(e.target.value)}
                                placeholder="(555) 123-4567"
                                required
                                disabled={addLoading}
                            />
                        </div>
                        <div className="auth-form-group" style={{justifyContent: 'center'}}>
                            <label className="email-center-toggle" style={{marginTop: '0.25rem'}}>
                                <input
                                    type="checkbox"
                                    checked={addSubscribe}
                                    onChange={(e) => setAddSubscribe(e.target.checked)}
                                    disabled={addLoading}
                                />
                                <span className="email-center-toggle-slider"/>
                                <span className="email-center-toggle-label">Receive notifications</span>
                            </label>
                        </div>
                        <div style={{display: 'flex', gap: '0.75rem'}}>
                            <button
                                type="submit"
                                className="auth-form-submit"
                                disabled={addLoading || !addPhoneNumber.trim()}
                                style={{flex: 1}}
                            >
                                {addLoading ? (
                                    <>
                                        <span className="auth-spinner"/>
                                        Adding...
                                    </>
                                ) : (
                                    'Add Phone'
                                )}
                            </button>
                            <button
                                type="button"
                                className="auth-form-submit"
                                onClick={() => {
                                    setShowAddForm(false);
                                    setAddError(null);
                                }}
                                style={{flex: 1, background: '#fff', color: '#003366', border: '1px solid #003366'}}
                            >
                                Cancel
                            </button>
                        </div>
                    </form>
                </div>
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
