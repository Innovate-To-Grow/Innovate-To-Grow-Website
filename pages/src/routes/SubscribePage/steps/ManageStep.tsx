import {Link} from 'react-router';
import type {ContactEmail, ContactPhone, ProfileResponse} from '@/features/auth/api/types';
import {normalizeEmailAddress} from '@/features/auth/components/sections/internal/emailAddress';
import {formatPhoneDisplay} from '@/features/auth/components/sections/internal/helpers';

interface ManageStepProps {
  profile: ProfileResponse;
  contactEmails: ContactEmail[];
  contactPhones: ContactPhone[];
  savingId: string | null;
  message: string | null;
  onPrimaryEmailToggle: (subscribed: boolean) => Promise<void>;
  onContactEmailToggle: (contact: ContactEmail, subscribed: boolean) => Promise<void>;
  onContactPhoneToggle: (phone: ContactPhone, subscribed: boolean) => Promise<void>;
}

interface ToggleButtonProps {
  active: boolean;
  disabled: boolean;
  label: string;
  onToggle: () => void;
}

// A switch with a fixed name: screen readers announce its on/off state from aria-checked,
// so the name must not change with the state as well.
const ToggleButton = ({active, disabled, label, onToggle}: ToggleButtonProps) => (
  <button
    type="button"
    role="switch"
    className={`subscribe-toggle ${active ? 'is-active' : ''}`}
    onClick={onToggle}
    disabled={disabled}
    aria-label={label}
    aria-checked={active}
  >
    <span className="subscribe-toggle-knob" />
  </button>
);

const verifiedLabel = (verified: boolean) => (verified ? 'Verified' : 'Unverified');

export const ManageStep = ({
  profile,
  contactEmails,
  contactPhones,
  savingId,
  message,
  onPrimaryEmailToggle,
  onContactEmailToggle,
  onContactPhoneToggle,
}: ManageStepProps) => {
  const primaryEmail = normalizeEmailAddress(profile.email);

  return (
    <div className="itg-panel subscribe-section">
      <section className="subscribe-preference-group" aria-labelledby="subscribe-email-preferences">
        <h2 id="subscribe-email-preferences" className="subscribe-preference-heading">Email Newsletters</h2>
        <div className="subscribe-preference-list">
          {primaryEmail ? (
            <div className="subscribe-preference-item">
              <div className="subscribe-preference-copy">
                <span className="subscribe-manage-email-value">{primaryEmail}</span>
                <span className="subscribe-preference-meta">
                  Primary email - {verifiedLabel(profile.email_verified)}
                </span>
              </div>
              <div className="subscribe-manage-status">
                <ToggleButton
                  active={profile.email_subscribe}
                  disabled={savingId !== null}
                  label={`Newsletters for ${primaryEmail}`}
                  onToggle={() => void onPrimaryEmailToggle(!profile.email_subscribe)}
                />
                <span className="subscribe-manage-status-label" aria-hidden="true">Newsletters</span>
              </div>
            </div>
          ) : null}

          {contactEmails.map((contact) => (
            <div key={contact.id} className="subscribe-preference-item">
              <div className="subscribe-preference-copy">
                <span className="subscribe-manage-email-value">{contact.email_address}</span>
                <span className="subscribe-preference-meta">
                  {contact.email_type === 'secondary' ? 'Secondary email' : 'Other email'} - {verifiedLabel(contact.verified)}
                </span>
              </div>
              <div className="subscribe-manage-status">
                <ToggleButton
                  active={contact.subscribe}
                  disabled={savingId !== null}
                  label={`Newsletters for ${contact.email_address}`}
                  onToggle={() => void onContactEmailToggle(contact, !contact.subscribe)}
                />
                <span className="subscribe-manage-status-label" aria-hidden="true">Newsletters</span>
              </div>
            </div>
          ))}

          {!primaryEmail && contactEmails.length === 0 ? (
            <p className="subscribe-empty">No email addresses are connected to this account.</p>
          ) : null}
        </div>
      </section>

      <section className="subscribe-preference-group" aria-labelledby="subscribe-phone-preferences">
        <h2 id="subscribe-phone-preferences" className="subscribe-preference-heading">Text Messages</h2>
        {contactPhones.length > 0 ? (
          <div className="subscribe-preference-list">
            {contactPhones.map((phone) => {
              const phoneDisplay = formatPhoneDisplay(phone.phone_number);
              return (
                <div key={phone.id} className="subscribe-preference-item">
                  <div className="subscribe-preference-copy">
                    <span className="subscribe-manage-email-value">{phoneDisplay}</span>
                    <span className="subscribe-preference-meta">
                      {phone.region_display} - {verifiedLabel(phone.verified)}
                    </span>
                  </div>
                  <div className="subscribe-manage-status">
                    <ToggleButton
                      active={phone.subscribe}
                      disabled={savingId !== null}
                      label={`Text messages for ${phoneDisplay}`}
                      onToggle={() => void onContactPhoneToggle(phone, !phone.subscribe)}
                    />
                    <span className="subscribe-manage-status-label" aria-hidden="true">Text Messages</span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="subscribe-empty">No phone numbers are connected to this account.</p>
        )}
      </section>

      {message ? <div className="subscribe-alert success" role="status">{message}</div> : null}

      <Link to="/account" className="itg-btn itg-btn-outline subscribe-link">
        View My Account
      </Link>
    </div>
  );
};
