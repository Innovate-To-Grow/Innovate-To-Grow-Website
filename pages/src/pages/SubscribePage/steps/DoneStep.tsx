import {Link} from 'react-router-dom';

interface DoneStepProps {
  email: string;
}

export const DoneStep = ({email}: DoneStepProps) => (
  <div className="subscribe-page">
    <div className="subscribe-done">
      <h2>You're Subscribed!</h2>
      <p className="subscribe-done-subtitle">
        You'll receive updates and announcements at <strong>{email}</strong>.
      </p>
      <div className="subscribe-done-notice">
        Your subscription preferences have been updated for this email.
      </div>
      <Link to="/account" className="subscribe-link">
        View My Account
      </Link>
    </div>
  </div>
);
