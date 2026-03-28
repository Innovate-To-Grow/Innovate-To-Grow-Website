import type {ProfileResponse} from '../../../services/auth';

interface PrimaryEmailCardProps {
  profile: ProfileResponse;
  subscribeSaving: boolean;
  onToggleSubscribe: () => void;
}

export const PrimaryEmailCard = ({
  profile,
  subscribeSaving,
  onToggleSubscribe,
}: PrimaryEmailCardProps) => (
  <div className="email-center-card">
    <div className="email-center-row">
      <div style={{flex: 1, minWidth: 0}}>
        <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap'}}>
          <span style={{fontWeight: 600, color: '#1f2937', wordBreak: 'break-all'}}>{profile.email}</span>
          <span className="email-center-badge primary">Primary</span>
        </div>
      </div>
      <label className="email-center-toggle" aria-label="Subscribe primary email">
        <input type="checkbox" checked={profile.email_subscribe} onChange={onToggleSubscribe} disabled={subscribeSaving} />
        <span className="email-center-toggle-slider" />
        <span className="email-center-toggle-label">Subscribe</span>
      </label>
    </div>
  </div>
);
