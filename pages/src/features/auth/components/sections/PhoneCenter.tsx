import {PhoneAddForm} from './PhoneAddForm';
import {PhoneCard} from './PhoneCard';
import {PhonePendingVerifyPanel} from './PhonePendingVerifyPanel';
import {StatusAlert} from '../shared/StatusAlert';
import {usePhoneCenter} from './internal/usePhoneCenter';

export const PhoneCenter = () => {
    const pc = usePhoneCenter();

    return (
        <div className="account-section">
            <h2 className="account-section-title">Phone Numbers</h2>

            {pc.successMessage ? <StatusAlert tone="success" message={pc.successMessage} style={{marginBottom: '1rem'}} /> : null}
            {pc.error ? <StatusAlert tone="error" message={pc.error} style={{marginBottom: '1rem'}} /> : null}

            {pc.loading ? (
                <p className="account-status-text">Loading phone numbers...</p>
            ) : (
                pc.phones.map((phone) => (
                    <PhoneCard
                        key={phone.id}
                        phone={phone}
                        verifyingId={pc.verifyingId}
                        verifyCode={pc.verifyCode}
                        verifyLoading={pc.verifyLoading}
                        verifyError={pc.verifyError}
                        resendLoading={pc.resendLoading}
                        onToggleSubscribe={pc.handleSubscribeToggle}
                        onToggleVerify={pc.handleToggleVerify}
                        onVerifyCodeChange={pc.setVerifyCode}
                        onVerifySubmit={pc.handleVerifySubmit}
                        onResend={pc.handleResend}
                        onCancelVerify={pc.handleCancelVerify}
                        onDelete={pc.handleDelete}
                    />
                ))
            )}

            {!pc.loading && pc.phones.length === 0 && !pc.showAddForm && (
                <p className="account-status-text account-status-text--spaced">
                    No phone numbers added yet.
                </p>
            )}

            {pc.showAddForm && pc.pendingNewPhone ? (
                <PhonePendingVerifyPanel
                    phone={pc.pendingNewPhone}
                    verifyCode={pc.verifyCode}
                    verifyLoading={pc.verifyLoading}
                    verifyError={pc.verifyError}
                    resendLoading={pc.resendLoading}
                    abandonLoading={pc.abandonPendingLoading}
                    onVerifyCodeChange={pc.setVerifyCode}
                    onVerifySubmit={pc.handleVerifySubmit}
                    onResend={pc.handleResendPendingPhone}
                    onAbandon={() => void pc.handleAbandonPendingPhone()}
                />
            ) : pc.showAddForm ? (
                <PhoneAddForm
                    addRegion={pc.addRegion}
                    addPhoneNumber={pc.addPhoneNumber}
                    addSubscribe={pc.addSubscribe}
                    addLoading={pc.addLoading}
                    addError={pc.addError}
                    onRegionChange={pc.handleAddRegionChange}
                    onPhoneNumberChange={pc.setAddPhoneNumber}
                    onSubscribeChange={pc.setAddSubscribe}
                    onSubmit={pc.handleAddSubmit}
                    onCancel={() => {
                        pc.setShowAddForm(false);
                        pc.setAddError(null);
                    }}
                />
            ) : (
                <button
                    type="button"
                    className="auth-form-submit account-action-primary account-action-primary--inline"
                    onClick={pc.beginAddPhoneFlow}
                >
                    Add Phone
                </button>
            )}
        </div>
    );
};
