import {Link} from 'react-router-dom';
import type {ContactEmail, ContactPhone, ProfileResponse} from '@/features/auth/api/types';
import {formatPhoneDisplay} from '@/features/auth/components/sections/internal/helpers';

interface ManageStepProps {
  profile: ProfileResponse | null;
  contactEmails: ContactEmail[];
  contactPhones: ContactPhone[];
  loading: boolean;
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

const ToggleButton = ({active, disabled, label, onToggle}: ToggleButtonProps) => (
  <button
    type="button"
    className={`subscribe-toggle ${active ? 'is-active' : ''}`}
    onClick={onToggle}
    disabled={disabled}
    aria-label={label}
    aria-pressed={active}
  >
    <span className="subscribe-toggle-knob" />
  </button>
);

const verifiedLabel = (verified: boolean) => (verified ? 'Verified' : 'Unverified');

export const ManageStep = ({
  profile,
  contactEmails,
  contactPhones,
  loading,
  savingId,
  message,
  onPrimaryEmailToggle,
  onContactEmailToggle,
  onContactPhoneToggle,
}: ManageStepProps) => {
  if (loading || !profile) {
    return (
      <div className="subscribe-section">
        <p className="subscribe-hint">Loading subscription preferences...</p>
      </div>
    );
  }

  return (
    <div className="subscribe-section">
      <section className="subscribe-preference-group" aria-labelledby="subscribe-email-preferences">
        <h3 id="subscribe-email-preferences" className="subscribe-preference-heading">Email Newsletters</h3>
        <div className="subscribe-preference-list">
          <div className="subscribe-preference-item">
            <div className="subscribe-preference-copy">
              <span className="subscribe-manage-email-value">{profile.email}</span>
              <span className="subscribe-preference-meta">
                Primary email - {verifiedLabel(profile.email_verified)}
              </span>
            </div>
            <div className="subscribe-manage-status">
              <span className="subscribe-manage-status-label">Newsletters</span>
              <ToggleButton
                active={profile.email_subscribe}
                disabled={savingId !== null}
                label={
                  profile.email_subscribe ? 'Turn off newsletter subscription' : 'Turn on newsletter subscription'
                }
                onToggle={() => void onPrimaryEmailToggle(!profile.email_subscribe)}
              />
            </div>
          </div>

          {contactEmails.map((contact) => (
            <div key={contact.id} className="subscribe-preference-item">
              <div className="subscribe-preference-copy">
                <span className="subscribe-manage-email-value">{contact.email_address}</span>
                <span className="subscribe-preference-meta">
                  {contact.email_type === 'secondary' ? 'Secondary email' : 'Other email'} - {verifiedLabel(contact.verified)}
                </span>
              </div>
              <div className="subscribe-manage-status">
                <span className="subscribe-manage-status-label">Newsletters</span>
                <ToggleButton
                  active={contact.subscribe}
                  disabled={savingId !== null}
                  label={
                    contact.subscribe
                      ? `Turn off newsletter subscription for ${contact.email_address}`
                      : `Turn on newsletter subscription for ${contact.email_address}`
                  }
                  onToggle={() => void onContactEmailToggle(contact, !contact.subscribe)}
                />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="subscribe-preference-group" aria-labelledby="subscribe-phone-preferences">
        <h3 id="subscribe-phone-preferences" className="subscribe-preference-heading">Text Messages</h3>
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
                    <span className="subscribe-manage-status-label">Text Messages</span>
                    <ToggleButton
                      active={phone.subscribe}
                      disabled={savingId !== null}
                      label={
                        phone.subscribe
                          ? `Turn off text messages for ${phoneDisplay}`
                          : `Turn on text messages for ${phoneDisplay}`
                      }
                      onToggle={() => void onContactPhoneToggle(phone, !phone.subscribe)}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="subscribe-empty">No phone numbers are connected to this account.</p>
        )}
      </section>

      {message ? <div className="subscribe-alert success">{message}</div> : null}

      <Link to="/account" className="subscribe-link">
        View My Account
      </Link>
    </div>
  );
};
