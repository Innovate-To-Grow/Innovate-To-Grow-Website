import {useState, useEffect, type FormEvent} from 'react';
import {useNavigate} from 'react-router-dom';
import {useAuth} from '../AuthContext';
import {
    getProfile,
    updateProfileFields,
    uploadProfileImage,
    type ProfileResponse,
} from '../../../services/auth';
import {fetchMyTickets, resendTicketEmail, type Registration} from '../../../services/api/events';
import {EmailCenter} from '../sections/EmailCenter';
import {PhoneCenter} from '../sections/PhoneCenter';
import '../Auth.css';

export const AccountPage = () => {
    const {isAuthenticated, logout, user, requiresProfileCompletion} = useAuth();
    const navigate = useNavigate();

    // Profile state
    const [profile, setProfile] = useState<ProfileResponse | null>(null);
    const [profileLoading, setProfileLoading] = useState(true);

    // Profile Image state
    const [profileImage, setProfileImage] = useState<string | null>(null);
    const [imageUploading, setImageUploading] = useState(false);
    const [imageError, setImageError] = useState<string | null>(null);

    // Profile form state
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [displayName, setDisplayName] = useState('');
    const [organization, setOrganization] = useState('');
    const [profileSaving, setProfileSaving] = useState(false);
    const [profileMessage, setProfileMessage] = useState<string | null>(null);
    const [profileError, setProfileError] = useState<string | null>(null);
    const [isEditingProfile, setIsEditingProfile] = useState(false);

    // Tickets state
    const [tickets, setTickets] = useState<Registration[]>([]);
    const [ticketsLoading, setTicketsLoading] = useState(true);
    const [resendingId, setResendingId] = useState<string | null>(null);

    // Auth guard
    useEffect(() => {
        if (!isAuthenticated) {
            navigate('/login', {replace: true});
            return;
        }
        if (requiresProfileCompletion) {
            navigate('/complete-profile', {replace: true});
        }
    }, [isAuthenticated, navigate, requiresProfileCompletion]);

    // Fetch profile on mount
    useEffect(() => {
        if (!isAuthenticated || requiresProfileCompletion) return;

        const fetchProfile = async () => {
            try {
                const data = await getProfile();
                setProfile(data);
                setFirstName(data.first_name ?? '');
                setLastName(data.last_name ?? '');
                setDisplayName(data.display_name ?? '');
                setOrganization(data.organization ?? '');
                setProfileError(null);
                if (data.profile_image) {
                    setProfileImage(data.profile_image);
                }
            } catch (err: unknown) {
                console.error('[AccountPage] Profile fetch failed:', err);
                // Populate from user context when profile API fails
                if (user?.display_name) {
                    setDisplayName(user.display_name);
                }
                setProfileError(getErrorMessage(err));
            } finally {
                setProfileLoading(false);
            }
        };

        fetchProfile();
    }, [isAuthenticated, requiresProfileCompletion, user?.display_name]);

    // Fetch tickets on mount
    useEffect(() => {
        if (!isAuthenticated || requiresProfileCompletion) return;

        const loadTickets = async () => {
            try {
                const data = await fetchMyTickets();
                setTickets(data);
            } catch {
                // Non-critical: silently fail
            } finally {
                setTicketsLoading(false);
            }
        };

        loadTickets();
    }, [isAuthenticated, requiresProfileCompletion]);

    const handleResendTicketEmail = async (registrationId: string) => {
        setResendingId(registrationId);
        try {
            await resendTicketEmail(registrationId);
            // Refresh tickets to update email status
            const updated = await fetchMyTickets();
            setTickets(updated);
        } catch {
            // Could show error, but keeping it simple
        } finally {
            setResendingId(null);
        }
    };

    const handleImageChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        // Basic validation
        if (!file.type.startsWith('image/')) {
            setImageError('Please select an image file.');
            return;
        }

        if (file.size > 5 * 1024 * 1024) { // 5MB limit
            setImageError('Image size should be less than 5MB.');
            return;
        }

        setImageUploading(true);
        setImageError(null);
        setProfileMessage(null);

        try {
            const updatedProfile = await uploadProfileImage(file);
            setProfile(updatedProfile);
            if (updatedProfile.profile_image) {
                setProfileImage(updatedProfile.profile_image);
            }
            setProfileMessage('Profile image updated successfully.');
            setImageError(null);
            e.target.value = '';
        } catch (err: unknown) {
            const message = getErrorMessage(err);
            setImageError(message);
        } finally {
            setImageUploading(false);
        }
    };

    const handleProfileSubmit = async (e: FormEvent) => {
        e.preventDefault();
        setProfileSaving(true);
        setProfileMessage(null);
        setProfileError(null);

        try {
            const updated = await updateProfileFields({
                first_name: firstName.trim(),
                last_name: lastName.trim(),
                display_name: displayName.trim(),
                organization: organization.trim(),
            });
            setProfile(updated);
            setProfileMessage('Profile updated successfully.');
            setIsEditingProfile(false);
        } catch (err: unknown) {
            const message = getErrorMessage(err);
            setProfileError(message);
        } finally {
            setProfileSaving(false);
        }
    };

    if (!isAuthenticated || requiresProfileCompletion) return null;

    // Use profile data if available, otherwise fall back to user context
    const displayEmail = profile?.email || user?.email;

    if (profileLoading) {
        return (
            <div className="account-page">
                <div className="account-section">
                    <p style={{textAlign: 'center', color: '#6b7280'}}>Loading profile...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="account-page">
            <h1 className="account-page-title">Account Dashboard</h1>

            <div className="account-grid">
                <div className="account-column">
                    {/* Profile Information */}
                    <div className="account-section">
                        <h2 className="account-section-title">Profile Information</h2>

                        <div className="profile-image-section">
                            <div className="profile-image-container">
                                {profileImage ? (
                                    <img
                                        src={profileImage}
                                        alt="Profile"
                                        className="profile-image-preview"
                                    />
                                ) : (
                                    <div className="profile-image-placeholder">
                      <span className="profile-image-initials">
                        {firstName && lastName
                            ? `${firstName[0]}${lastName[0]}`.toUpperCase()
                            : (displayName ? displayName[0].toUpperCase() : 'U')}
                      </span>
                                    </div>
                                )}

                                <label htmlFor="profile-image-upload" className="profile-image-upload-btn"
                                       aria-label="Upload photo">
                                    {imageUploading ? (
                                        <i className="fa fa-spinner fa-spin" aria-hidden/>
                                    ) : (
                                        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                                            <path
                                                d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/>
                                        </svg>
                                    )}
                                </label>
                                <input
                                    id="profile-image-upload"
                                    type="file"
                                    accept="image/*"
                                    onChange={handleImageChange}
                                    style={{display: 'none'}}
                                    disabled={imageUploading}
                                />
                            </div>
                            {imageError && !imageError.trim().startsWith('<') && (
                                <p className="profile-image-error">{imageError}</p>
                            )}
                        </div>

                        {profileMessage && (
                            <div className="auth-alert success">
                                <i className="fa fa-check-circle auth-alert-icon"/>
                                <span>{profileMessage}</span>
                            </div>
                        )}

                        {profileError && (
                            <div className="auth-alert error" style={{flexWrap: 'wrap', gap: '0.5rem'}}>
                                <i className="fa fa-exclamation-circle auth-alert-icon" aria-hidden/>
                                <span style={{flex: 1, minWidth: 0}}>{profileError}</span>
                                <button
                                    type="button"
                                    className="auth-verify-resend"
                                    style={{padding: '0.4rem 0.8rem', fontSize: '0.8rem', flexShrink: 0}}
                                    onClick={async () => {
                                        setProfileError(null);
                                        setProfileLoading(true);
                                        try {
                                            const data = await getProfile();
                                            setProfile(data);
                                            setFirstName(data.first_name ?? '');
                                            setLastName(data.last_name ?? '');
                                            setDisplayName(data.display_name ?? '');
                                            setOrganization(data.organization ?? '');
                                            if (data.profile_image) setProfileImage(data.profile_image);
                                        } catch (err: unknown) {
                                            console.error('[AccountPage] Profile fetch failed:', err);
                                            if (user?.display_name) setDisplayName(user.display_name);
                                            setProfileError(getErrorMessage(err));
                                        } finally {
                                            setProfileLoading(false);
                                        }
                                    }}
                                >
                                    Retry
                                </button>
                            </div>
                        )}

                        <form className="auth-form" onSubmit={handleProfileSubmit}>
                            <div className="account-form-row">
                                <div className="auth-form-group">
                                    <label className="auth-form-label" htmlFor="account-first-name">
                                        First Name
                                    </label>
                                    <input
                                        id="account-first-name"
                                        type="text"
                                        className="auth-form-input"
                                        value={firstName}
                                        onChange={(e) => setFirstName(e.target.value)}
                                        autoComplete="given-name"
                                        disabled={!isEditingProfile}
                                    />
                                </div>

                                <div className="auth-form-group">
                                    <label className="auth-form-label" htmlFor="account-last-name">
                                        Last Name
                                    </label>
                                    <input
                                        id="account-last-name"
                                        type="text"
                                        className="auth-form-input"
                                        value={lastName}
                                        onChange={(e) => setLastName(e.target.value)}
                                        autoComplete="family-name"
                                        disabled={!isEditingProfile}
                                    />
                                </div>
                            </div>

                            <div className="auth-form-group">
                                <label className="auth-form-label" htmlFor="account-display-name">
                                    Display Name
                                </label>
                                <input
                                    id="account-display-name"
                                    type="text"
                                    className="auth-form-input"
                                    value={displayName}
                                    onChange={(e) => setDisplayName(e.target.value)}
                                    disabled={!isEditingProfile}
                                />
                            </div>

                            <div className="auth-form-group">
                                <label className="auth-form-label" htmlFor="account-organization">
                                    Organization
                                </label>
                                <input
                                    id="account-organization"
                                    type="text"
                                    className="auth-form-input"
                                    value={organization}
                                    onChange={(e) => setOrganization(e.target.value)}
                                    placeholder="Company or organization"
                                    autoComplete="organization"
                                    disabled={!isEditingProfile}
                                />
                            </div>

                            {isEditingProfile ? (
                                <div style={{display: 'flex', gap: '1rem'}}>
                                    <button
                                        type="submit"
                                        className="auth-form-submit account-edit-btn"
                                        disabled={profileSaving}
                                        style={{flex: 1}}
                                    >
                                        {profileSaving ? (
                                            <>
                                                <span className="auth-spinner"/>
                                                Saving...
                                            </>
                                        ) : (
                                            'Save Profile'
                                        )}
                                    </button>
                                    <button
                                        type="button"
                                        className="account-edit-btn"
                                        onClick={() => {
                                            setIsEditingProfile(false);
                                            setFirstName(profile?.first_name || '');
                                            setLastName(profile?.last_name || '');
                                            setDisplayName(profile?.display_name || '');
                                            setOrganization(profile?.organization || '');
                                            setProfileMessage(null);
                                            setProfileError(null);
                                        }}
                                        style={{flex: 1}}
                                    >
                                        Cancel
                                    </button>
                                </div>
                            ) : (
                                <button
                                    type="button"
                                    className="account-edit-btn"
                                    onClick={() => setIsEditingProfile(true)}
                                >
                                    Edit Profile
                                </button>
                            )}
                        </form>
                    </div>

                </div>

                <div className="account-column">
                    {/* Subscriptions */}
                    {profile && <EmailCenter profile={profile} onProfileUpdate={setProfile}/>}

                    {/* Phone Numbers */}
                    {profile && <PhoneCenter/>}

                    {/* My Tickets */}
                    <div className="account-section">
                        <h2 className="account-section-title">My Tickets</h2>
                        {ticketsLoading ? (
                            <p style={{color: '#6b7280', fontSize: '0.9rem'}}>Loading tickets...</p>
                        ) : tickets.length === 0 ? (
                            <p style={{color: '#6b7280', fontSize: '0.9rem'}}>No event tickets yet.</p>
                        ) : (
                            <div style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
                                {tickets.map((t) => (
                                    <div key={t.id} style={{padding: '1rem', borderRadius: '10px', background: '#f8fafc', border: '1px solid #dbe3ef'}}>
                                        <div style={{fontWeight: 700, color: '#003366', marginBottom: '0.5rem'}}>{t.event.name}</div>
                                        <div style={{fontSize: '0.85rem', color: '#374151', marginBottom: '0.25rem'}}>
                                            <strong>Date:</strong> {new Date(t.event.date + 'T00:00:00').toLocaleDateString('en-US', {year: 'numeric', month: 'long', day: 'numeric'})}
                                        </div>
                                        <div style={{fontSize: '0.85rem', color: '#374151', marginBottom: '0.25rem'}}>
                                            <strong>Location:</strong> {t.event.location}
                                        </div>
                                        <div style={{fontSize: '0.85rem', color: '#374151', marginBottom: '0.25rem'}}>
                                            <strong>Ticket:</strong> {t.ticket.name}
                                        </div>
                                        <div style={{fontSize: '1.1rem', fontWeight: 700, color: '#003366', margin: '0.5rem 0', letterSpacing: '0.04em'}}>
                                            {t.ticket_code}
                                        </div>
                                        <div style={{textAlign: 'center', margin: '0.75rem 0'}}>
                                            <img src={t.barcode_image} alt="Ticket barcode" style={{maxWidth: '100%', borderRadius: '6px', border: '1px solid #e5e7eb', padding: '8px', background: '#fff'}} />
                                        </div>
                                        <div style={{fontSize: '0.8rem', color: '#6b7280', marginBottom: '0.5rem'}}>
                                            {t.ticket_email_sent_at
                                                ? `Email sent ${new Date(t.ticket_email_sent_at).toLocaleString()}`
                                                : t.ticket_email_error
                                                    ? `Email failed: ${t.ticket_email_error}`
                                                    : 'Email not sent'}
                                        </div>
                                        <button
                                            type="button"
                                            className="account-edit-btn"
                                            style={{fontSize: '0.8rem', padding: '0.4rem 0.8rem'}}
                                            disabled={resendingId === t.id}
                                            onClick={() => handleResendTicketEmail(t.id)}
                                        >
                                            {resendingId === t.id ? 'Sending...' : 'Resend Ticket Email'}
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Account Details */}
                    <div className="account-section">
                        <h2 className="account-section-title">Account Details</h2>

                        <div className="account-details-rows">
                            <div className="account-readonly-group">
                                <span className="auth-form-label">Email</span>
                                <span className="account-readonly-value">{displayEmail}</span>
                            </div>

                            {profile?.date_joined && (
                                <div className="account-readonly-group">
                                    <span className="auth-form-label">Member Since</span>
                                    <span className="account-readonly-value">
                    {new Date(profile.date_joined).toLocaleDateString()}
                  </span>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Sign Out */}
                    <div className="account-section">
                        <button
                            type="button"
                            className="profile-logout"
                            onClick={logout}
                        >
                            <i className="fa fa-sign-out" style={{marginRight: '0.5rem'}}/>
                            Sign Out
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

function getErrorMessage(err: unknown): string {
    if (typeof err === 'object' && err !== null) {
        const axiosError = err as { response?: { data?: Record<string, unknown> } };
        if (axiosError.response?.data) {
            const data = axiosError.response.data;
            const firstKey = Object.keys(data)[0];
            if (firstKey) {
                const value = data[firstKey];
                if (Array.isArray(value)) {
                    return value[0] as string;
                }
                if (typeof value === 'string') {
                    return value;
                }
            }
        }
    }
    return 'An unexpected error occurred. Please try again.';
}
