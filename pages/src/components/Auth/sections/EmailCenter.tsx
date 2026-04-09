import {
    type ProfileResponse,
} from '../../../services/auth';
import {EmailAddForm} from './EmailAddForm';
import {ContactEmailCard} from './ContactEmailCard';
import {PrimaryEmailCard} from './PrimaryEmailCard';
import {StatusAlert} from '../shared/StatusAlert';
import {useEmailCenter} from './internal/useEmailCenter';
import '../Auth.css';
interface EmailCenterProps {
    profile: ProfileResponse;
    onProfileUpdate: (updated: ProfileResponse) => void;
}

export const EmailCenter = ({profile, onProfileUpdate}: EmailCenterProps) => {
    const emailCenter = useEmailCenter({profile, onProfileUpdate});

    return (
        <div className="account-section">
            <h2 className="account-section-title">Emails</h2>

            {emailCenter.successMessage ? <StatusAlert tone="success" message={emailCenter.successMessage} style={{marginBottom: '1rem'}} /> : null}
            {emailCenter.error ? <StatusAlert tone="error" message={emailCenter.error} style={{marginBottom: '1rem'}} /> : null}

            <PrimaryEmailCard
                profile={profile}
                subscribeSaving={emailCenter.subscribeSaving}
                verifying={emailCenter.primaryVerifying}
                verifyCode={emailCenter.primaryVerifyCode}
                verifyLoading={emailCenter.primaryVerifyLoading}
                verifyError={emailCenter.primaryVerifyError}
                resendLoading={emailCenter.primaryResendLoading}
                onToggleSubscribe={emailCenter.handlePrimarySubscribeToggle}
                onToggleVerify={emailCenter.handlePrimaryToggleVerify}
                onVerifyCodeChange={emailCenter.setPrimaryVerifyCode}
                onVerifySubmit={emailCenter.handlePrimaryVerifySubmit}
                onResend={emailCenter.handlePrimaryResend}
                onCancelVerify={emailCenter.handlePrimaryCancelVerify}
            />

            {emailCenter.loading ? (
                <p className="account-status-text">Loading connected emails...</p>
            ) : (
                emailCenter.contactEmails.map((contact) => (
                    <ContactEmailCard
                        key={contact.id}
                        contact={contact}
                        verifyingId={emailCenter.verifyingId}
                        verifyCode={emailCenter.verifyCode}
                        verifyLoading={emailCenter.verifyLoading}
                        verifyError={emailCenter.verifyError}
                        resendLoading={emailCenter.resendLoading}
                        onContactTypeChange={emailCenter.handleContactTypeChange}
                        onContactSubscribeToggle={emailCenter.handleContactSubscribeToggle}
                        onToggleVerify={(contactId) => {
                            emailCenter.setVerifyingId(emailCenter.verifyingId === contactId ? null : contactId);
                            emailCenter.setVerifyCode('');
                            emailCenter.setVerifyError(null);
                        }}
                        onVerifyCodeChange={emailCenter.setVerifyCode}
                        onVerifySubmit={emailCenter.handleVerifySubmit}
                        onResend={emailCenter.handleResend}
                        onDelete={emailCenter.handleDelete}
                        onCancelVerify={() => {
                            emailCenter.setVerifyingId(null);
                            emailCenter.setVerifyCode('');
                            emailCenter.setVerifyError(null);
                        }}
                        onMakePrimary={emailCenter.handleMakePrimary}
                        makePrimaryLoadingId={emailCenter.makePrimaryLoadingId}
                        secondaryDisabled={emailCenter.hasSecondaryEmail}
                    />
                ))
            )}

            {emailCenter.showAddForm ? (
                <EmailAddForm
                    addEmail={emailCenter.addEmail}
                    addType={emailCenter.addType}
                    addSubscribe={emailCenter.addSubscribe}
                    addLoading={emailCenter.addLoading}
                    addError={emailCenter.addError}
                    secondaryDisabled={emailCenter.hasSecondaryEmail}
                    onEmailChange={emailCenter.setAddEmail}
                    onTypeChange={emailCenter.setAddType}
                    onSubscribeChange={emailCenter.setAddSubscribe}
                    onSubmit={emailCenter.handleAddSubmit}
                    onCancel={() => {
                        emailCenter.setShowAddForm(false);
                        emailCenter.setAddError(null);
                    }}
                />
            ) : (
                <button
                    type="button"
                    className="auth-form-submit account-action-primary account-action-primary--inline"
                    onClick={() => {
                        emailCenter.setShowAddForm(true);
                        emailCenter.setAddType(emailCenter.hasSecondaryEmail ? 'other' : 'secondary');
                        emailCenter.clearMessages();
                    }}
                >
                    Add Email
                </button>
            )}
        </div>
    );
};
