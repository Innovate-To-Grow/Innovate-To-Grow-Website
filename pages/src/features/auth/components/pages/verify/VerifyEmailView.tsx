import {Icon} from '@/components/Icon/Icon';
import {MESSAGE_ID, type VerifyEmailViewProps} from './verifyEmailViewProps';
import {NewPasswordForm, VerifyCodeForm} from './VerifyEmailForms';

type VerifyAlertsProps = Pick<VerifyEmailViewProps, 'localMessage' | 'localSuccess' | 'error'>;

const VerifyAlerts = ({localMessage, localSuccess, error}: VerifyAlertsProps) => (
  <>
  {localMessage ? (
    <div className="auth-alert-wrapper">
      <div className="auth-alert info" role="status">
        <Icon name="info-circle" className="auth-alert-icon" />
        <span id={MESSAGE_ID}>{localMessage}</span>
      </div>
    </div>
  ) : null}

  {localSuccess ? (
    <div className="auth-alert-wrapper">
      <div className="auth-alert success" role="status">
        <Icon name="check-circle" className="auth-alert-icon" />
        <span>{localSuccess}</span>
      </div>
    </div>
  ) : null}

  {error ? (
    <div className="auth-alert-wrapper">
      <div className="auth-alert error" role="alert">
        <Icon name="exclamation-circle" className="auth-alert-icon" />
        <span>{error}</span>
      </div>
    </div>
  ) : null}
  </>
);

export const VerifyEmailView = (props: VerifyEmailViewProps) => (
  <div className="auth-page">
    <header className="auth-page-header">
      <h1 className="itg-page-title auth-page-title">{props.title}</h1>
      <p className="itg-page-meta auth-page-subtitle">{props.subtitle}</p>
    </header>
    <div className="itg-panel auth-page-card">

      <div className="auth-verification-intro">
        <span className="auth-verification-label">Code sent to</span>
        <strong>{props.email}</strong>
      </div>

      <VerifyAlerts {...props} />

      {props.verificationToken ? <NewPasswordForm {...props} /> : <VerifyCodeForm {...props} />}
    </div>
  </div>
);
