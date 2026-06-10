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
        By checking, you consent to receive course updates and educational reminders from University of California,
        Merced. Message frequency may vary. Message and data rates may apply, reply HELP for help or STOP to opt-out.
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
        By checking, I accept{' '}
        <a
          href="https://i2g.ucmerced.edu/privacy"
          className="phone-add-consent-link"
          target="_blank"
          rel="noreferrer"
          onClick={(event) => event.stopPropagation()}
        >
          Terms of Service
        </a>{' '}
        &amp;{' '}
        <a
          href="https://www.ucmerced.edu/privacy-statement"
          className="phone-add-consent-link"
          target="_blank"
          rel="noreferrer"
          onClick={(event) => event.stopPropagation()}
        >
          Privacy Policy
        </a>
        .
      </span>
    </label>
  </div>
);
