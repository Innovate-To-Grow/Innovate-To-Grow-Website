import {DeleteAccountSection} from './account/DeleteAccountSection';
import {DetailsSection} from './account/DetailsSection';
import {PasswordSection} from './account/PasswordSection';
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
                <div className="account-column account-column--primary">
                    <ProfileSection
                        firstName={account.firstName}
                        middleName={account.middleName}
                        lastName={account.lastName}
                        organizationType={account.organizationType}
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
                        onOrganizationTypeChange={(value) => {
                            account.setOrganizationType(value);
                            account.setOrganization('');
                        }}
                        onOrganizationChange={account.setOrganization}
                        onRetryProfile={() => void account.loadProfile()}
                        onStartEditing={() => account.setIsEditingProfile(true)}
                        onCancelEditing={account.handleCancelEditing}
                    />
                    <TicketsSection
                        tickets={account.tickets}
                        ticketsLoading={account.ticketsLoading}
                        resendingId={account.resendingId}
                        onResendTicketEmail={(registrationId) => void account.handleResendTicketEmail(registrationId)}
                    />
                </div>

                <div className="account-column account-column--secondary">
                    {account.profile ? <EmailCenter profile={account.profile} onProfileUpdate={account.setProfile}/> : null}
                    {account.profile ? <PhoneCenter/> : null}
                    <DetailsSection displayEmail={account.displayEmail} dateJoined={account.profile?.date_joined}/>
                    <PasswordSection
                        passwordCodeRequested={account.passwordCodeRequested}
                        passwordCode={account.passwordCode}
                        passwordVerificationToken={account.passwordVerificationToken}
                        newPassword={account.newPassword}
                        confirmPassword={account.confirmPassword}
                        passwordLoading={account.passwordLoading}
                        passwordMessage={account.passwordMessage}
                        passwordError={account.passwordError}
                        onPasswordRequestCode={account.handlePasswordRequestCode}
                        onPasswordVerifyCode={account.handlePasswordVerifyCode}
                        onPasswordConfirm={account.handlePasswordConfirm}
                        onPasswordCodeChange={account.setPasswordCode}
                        onNewPasswordChange={account.setNewPassword}
                        onConfirmPasswordChange={account.setConfirmPassword}
                    />
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
                    <DeleteAccountSection
                        deleteCodeRequested={account.deleteCodeRequested}
                        deleteCode={account.deleteCode}
                        deleteVerificationToken={account.deleteVerificationToken}
                        deleteLoading={account.deleteLoading}
                        deleteMessage={account.deleteMessage}
                        deleteError={account.deleteError}
                        onDeleteRequestCode={account.handleDeleteRequestCode}
                        onDeleteVerifyCode={account.handleDeleteVerifyCode}
                        onDeleteConfirm={account.handleDeleteConfirm}
                        onDeleteCodeChange={account.setDeleteCode}
                    />
                </div>
            </div>
        </div>
    );
};
