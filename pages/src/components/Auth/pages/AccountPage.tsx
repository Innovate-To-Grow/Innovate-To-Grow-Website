import {DetailsSection} from './account/DetailsSection';
import {ProfileSection} from './account/ProfileSection';
import {TicketsSection} from './account/TicketsSection';
import {useAccountDashboard} from './account/useAccountDashboard';
import {EmailCenter} from '../sections/EmailCenter';
import {PhoneCenter} from '../sections/PhoneCenter';
import '../Auth.css';

export const AccountPage = () => {
    const account = useAccountDashboard();

    if (!account.canRender) return null;
    if (account.profileLoading) {
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
                    <ProfileSection
                        firstName={account.firstName}
                        middleName={account.middleName}
                        lastName={account.lastName}
                        organization={account.organization}
                        profileImage={account.profileImage}
                        imageUploading={account.imageUploading}
                        imageError={account.imageError}
                        profileSaving={account.profileSaving}
                        profileMessage={account.profileMessage}
                        profileError={account.profileError}
                        isEditingProfile={account.isEditingProfile}
                        onImageChange={account.handleImageChange}
                        onSubmit={account.handleProfileSubmit}
                        onFirstNameChange={account.setFirstName}
                        onMiddleNameChange={account.setMiddleName}
                        onLastNameChange={account.setLastName}
                        onOrganizationChange={account.setOrganization}
                        onRetryProfile={() => void account.loadProfile()}
                        onStartEditing={() => account.setIsEditingProfile(true)}
                        onCancelEditing={account.handleCancelEditing}
                    />
                </div>

                <div className="account-column">
                    {account.profile ? <EmailCenter profile={account.profile} onProfileUpdate={account.setProfile}/> : null}
                    {account.profile ? <PhoneCenter/> : null}
                    <TicketsSection
                        tickets={account.tickets}
                        ticketsLoading={account.ticketsLoading}
                        resendingId={account.resendingId}
                        onResendTicketEmail={(registrationId) => void account.handleResendTicketEmail(registrationId)}
                    />
                    <DetailsSection displayEmail={account.displayEmail} dateJoined={account.profile?.date_joined}/>
                    <div className="account-section">
                        <button
                            type="button"
                            className="profile-logout"
                            onClick={account.logout}
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
