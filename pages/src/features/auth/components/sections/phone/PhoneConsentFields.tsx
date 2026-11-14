import {Link} from 'react-router';

interface PhoneConsentFieldsProps {
  idPrefix: string;
  smsConsent: boolean;
  termsAccepted: boolean;
  disabled?: boolean;
  onSmsConsentChange: (checked: boolean) => void;
  onTermsAcceptedChange: (checked: boolean) => void;
}

export const PhoneConsentFields = ({
  idPrefix,
  smsConsent,
  termsAccepted,
  disabled = false,
  onSmsConsentChange,
  onTermsAcceptedChange,
}: PhoneConsentFieldsProps) => (
  <div className="phone-add-consent-group" aria-label="Phone consent options">
    <label className="phone-add-consent-option" htmlFor={`${idPrefix}-sms-consent`}>
      <input
        id={`${idPrefix}-sms-consent`}
        type="checkbox"
        checked={smsConsent}
        onChange={(event) => onSmsConsentChange(event.target.checked)}
        disabled={disabled}
      />
      <span>
        By checking, you agree to receive text messages from Innovate to Grow at UC Merced: event updates and
        reminders, and program announcements. Message frequency varies. Message and data rates may apply. Reply HELP
        for help or STOP to opt out.
      </span>
    </label>
    <label className="phone-add-consent-option" htmlFor={`${idPrefix}-terms`}>
      <input
        id={`${idPrefix}-terms`}
        type="checkbox"
        checked={termsAccepted}
        onChange={(event) => onTermsAcceptedChange(event.target.checked)}
        disabled={disabled}
        required
      />
      <span>
        By checking, I accept the Innovate to Grow{' '}
        <Link
          to="/privacy"
          className="phone-add-consent-link"
          target="_blank"
          rel="noreferrer"
          onClick={(event) => event.stopPropagation()}
        >
          Privacy/Legal Notice
        </Link>{' '}
        and the UC Merced{' '}
        <a
          href="https://www.ucmerced.edu/privacy-statement"
          className="phone-add-consent-link"
          target="_blank"
          rel="noreferrer"
          onClick={(event) => event.stopPropagation()}
        >
          Privacy Statement
        </a>
        .
      </span>
    </label>
  </div>
);
