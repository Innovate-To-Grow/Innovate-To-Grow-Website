import { Link } from 'react-router-dom';

interface PrivacyLegalNoticeProps {
  action?: string;
}

export const PrivacyLegalNotice = ({ action = 'continuing' }: PrivacyLegalNoticeProps) => (
  <p className="auth-help-text auth-legal-notice">
    By {action}, you acknowledge the Innovate to Grow{' '}
    <Link to="/privacy" className="auth-text-link auth-legal-notice-link">
      Privacy/Legal Notice
    </Link>
    , including how account contact details may be used for email and SMS communications.
  </p>
);
