import type {ContactPhone} from '../../../services/auth';
import {formatPhoneDisplay} from './internal/helpers';

interface PhoneCardProps {
  phone: ContactPhone;
  onToggleSubscribe: (phone: ContactPhone) => void;
  onDelete: (phoneId: string) => void;
}

export const PhoneCard = ({phone, onToggleSubscribe, onDelete}: PhoneCardProps) => (
  <div className="email-center-card">
    <div className="email-center-row">
      <div style={{flex: 1, minWidth: 0}}>
        <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap'}}>
          <span style={{fontWeight: 500, color: '#1f2937'}}>{formatPhoneDisplay(phone.phone_number, phone.region)}</span>
          <span className="email-center-badge primary">{phone.region_display}</span>
        </div>
        <div className="email-center-actions">
          <label className="email-center-toggle" aria-label="Receive notifications">
            <input type="checkbox" checked={phone.subscribe} onChange={() => onToggleSubscribe(phone)} />
            <span className="email-center-toggle-slider" />
            <span className="email-center-toggle-label">Notifications</span>
          </label>
          <button type="button" className="email-center-btn delete" onClick={() => onDelete(phone.id)}>
            Remove
          </button>
        </div>
      </div>
    </div>
  </div>
);
