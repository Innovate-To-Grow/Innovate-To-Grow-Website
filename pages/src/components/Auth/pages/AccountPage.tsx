import {useState, useEffect, type FormEvent} from 'react';
import {useNavigate} from 'react-router-dom';
import {useAuth} from '../AuthContext';
import {
    getProfile,
    getAccountEmails,
    updateProfileFields,
    uploadProfileImage,
    type ProfileResponse,
} from '../../../services/auth';
import {EmailCenter} from '../sections/EmailCenter';
import '../Auth.css';

export const AccountPage = () => {
    const {isAuthenticated, logout, user, requestPasswordChangeCode, requiresProfileCompletion} = useAuth();
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

    // Password form state
    const [authEmails, setAuthEmails] = useState<string[]>([]);
    const [codePasswordEmail, setCodePasswordEmail] = useState('');
    const [codePasswordLoading, setCodePasswordLoading] = useState(false);
    const [codePasswordMessage, setCodePasswordMessage] = useState<string | null>(null);
    const [codePasswordError, setCodePasswordError] = useState<string | null>(null);
    const [isPasswordOpen, setIsPasswordOpen] = useState(false);

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

    useEffect(() => {
        if (!isAuthenticated || requiresProfileCompletion) return;

        const fetchAccountEmails = async () => {
            try {
                const data = await getAccountEmails();
                setAuthEmails(data.emails);
                if (data.emails.length > 0) {
                    setCodePasswordEmail((current) => current || data.emails[0]);
                }
            } catch (err: unknown) {
                console.error('[AccountPage] Account email fetch failed:', err);
                if (user?.email) {
                    setAuthEmails([user.email]);
                    setCodePasswordEmail((current) => current || user.email);
                }
            }
        };

        fetchAccountEmails();
    }, [isAuthenticated, requiresProfileCompletion, user?.email]);

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

    const handleCodePasswordRequest = async () => {
        if (!codePasswordEmail) return;
        setCodePasswordLoading(true);
        setCodePasswordMessage(null);
        setCodePasswordError(null);

        try {
            const response = await requestPasswordChangeCode(codePasswordEmail);
            setCodePasswordMessage(response.message);
            navigate(`/verify-email?flow=change&email=${encodeURIComponent(codePasswordEmail)}`);
        } catch (err: unknown) {
            setCodePasswordError(getErrorMessage(err));
        } finally {
            setCodePasswordLoading(false);
        }
    };

    if (!isAuthenticated || requiresProfileCompletion) return null;

    // Use profile data if available, otherwise fall back to user context
    const displayEmail = profile?.email || user?.email;
    const displayUsername = profile?.username || user?.username;
    const availableAuthEmails = authEmails.length > 0 ? authEmails : (displayEmail ? [displayEmail] : []);

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

                    {/* Change Password */}
                    <div className="account-section">
                        <div className="account-section-header" onClick={() => setIsPasswordOpen(!isPasswordOpen)}>
                            <h2 className="account-section-title">Change Password</h2>
                            <span className="account-section-toggle">{isPasswordOpen ? '\u2212' : '+'}</span>
                        </div>

                        {isPasswordOpen && (<>
                            <p className="auth-help-text">
                                Send a 6-digit code to your primary email or any verified contact email linked to this
                                account.
                            </p>

                            {codePasswordMessage && (
                                <div className="auth-alert info">
                                    <i className="fa fa-info-circle auth-alert-icon"/>
                                    <span>{codePasswordMessage}</span>
                                </div>
                            )}

                            {codePasswordError && (
                                <div className="auth-alert error">
                                    <i className="fa fa-exclamation-circle auth-alert-icon"/>
                                    <span>{codePasswordError}</span>
                                </div>
                            )}

                            <div className="auth-form-group">
                                <label className="auth-form-label" htmlFor="code-password-email">
                                    Send Code To
                                </label>
                                <select
                                    id="code-password-email"
                                    className="auth-form-input auth-form-select"
                                    value={codePasswordEmail}
                                    onChange={(event) => {
                                        setCodePasswordEmail(event.target.value);
                                        setCodePasswordError(null);
                                    }}
                                    disabled={codePasswordLoading || availableAuthEmails.length === 0}
                                >
                                    {availableAuthEmails.map((email) => (
                                        <option key={email} value={email}>
                                            {email}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <button
                                type="button"
                                className="auth-form-submit"
                                disabled={codePasswordLoading || !codePasswordEmail}
                                onClick={handleCodePasswordRequest}
                            >
                                {codePasswordLoading ? (
                                    <>
                                        <span className="auth-spinner"/>
                                        Sending code...
                                    </>
                                ) : (
                                    'Send Verification Code'
                                )}
                            </button>
                        </>)}
                    </div>
                </div>

                <div className="account-column">
                    {/* Subscriptions */}
                    {profile && <EmailCenter profile={profile} onProfileUpdate={setProfile}/>}

                    {/* Account Details */}
                    <div className="account-section">
                        <h2 className="account-section-title">Account Details</h2>

                        <div className="account-details-rows">
                            <div className="account-readonly-group">
                                <span className="auth-form-label">Email</span>
                                <span className="account-readonly-value">{displayEmail}</span>
                            </div>

                            <div className="account-readonly-group">
                                <span className="auth-form-label">Username</span>
                                <span className="account-readonly-value">{displayUsername}</span>
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
