import {Link} from 'react-router';
import type {Registration} from '@/features/events/api';
import {resendTicketEmail} from '@/features/events/api';
import {formatEventDateRange} from '@/features/events/formatEventDateRange';
import {useState} from 'react';

interface DoneStateProps {
  registration: Registration;
  showChooseAnother?: boolean;
  onChooseAnother?: () => void;
}

export const DoneState = ({registration, showChooseAnother = false, onChooseAnother}: DoneStateProps) => {
  const [resending, setResending] = useState(false);
  const [resendMessage, setResendMessage] = useState('');

  const handleResend = async () => {
    setResending(true);
    setResendMessage('');
    try {
      await resendTicketEmail(registration.id);
      setResendMessage('Email sent successfully.');
    } catch {
      setResendMessage('Failed to send email. Please try again.');
    } finally {
      setResending(false);
    }
  };

  return (
    <section className="event-reg-done" aria-labelledby="event-reg-done-title">
      <h2 id="event-reg-done-title" className="itg-section-title event-reg-done-title">
        You're Registered!
      </h2>
      <p className="event-reg-done-subtitle">
        Your ticket for <strong>{registration.event.name}</strong> is confirmed.
      </p>

      <div className="itg-panel event-reg-ticket">
        <div className="event-reg-ticket-pass">
          <img src={registration.barcode_image} alt="Ticket barcode" className="event-reg-barcode" />
          <div className="event-reg-ticket-code">{registration.ticket_code}</div>
        </div>

        <div className="event-reg-done-details">
          <dl className="itg-meta-box event-reg-done-meta">
            <div className="itg-meta-item">
              <dt className="itg-meta-label">Name</dt>
              <dd className="itg-meta-value">{registration.attendee_name}</dd>
            </div>
            <div className="itg-meta-item">
              <dt className="itg-meta-label">Email</dt>
              <dd className="itg-meta-value">{registration.attendee_email}</dd>
            </div>
            <div className="itg-meta-item">
              <dt className="itg-meta-label">Ticket</dt>
              <dd className="itg-meta-value">{registration.ticket.name}</dd>
            </div>
            <div className="itg-meta-item">
              <dt className="itg-meta-label">Date</dt>
              <dd className="itg-meta-value">{formatEventDateRange(registration.event.date, registration.event.end_date)}</dd>
            </div>
            <div className="itg-meta-item">
              <dt className="itg-meta-label">Location</dt>
              <dd className="itg-meta-value">{registration.event.location}</dd>
            </div>
          </dl>
          {registration.event.description ? (
            <p className="event-reg-done-description">{registration.event.description}</p>
          ) : null}
        </div>
      </div>

      {registration.ticket_email_sent_at ? (
        <div className="event-reg-done-email-notice" role="status">
          A confirmation email was sent to {registration.attendee_email}
          {registration.attendee_secondary_email ? ` and ${registration.attendee_secondary_email}` : ''}.
        </div>
      ) : null}

      <div className="event-reg-done-actions">
        <Link to="/account" className="itg-btn itg-btn-primary">
          View My Account
        </Link>
        <button
          type="button"
          className="itg-btn itg-btn-outline"
          onClick={handleResend}
          disabled={resending}
        >
          {resending ? 'Sending...' : 'Resend Ticket Email'}
        </button>
        {showChooseAnother ? (
          <button type="button" className="itg-btn itg-btn-outline" onClick={onChooseAnother}>
            View Other Events
          </button>
        ) : null}
      </div>
      {resendMessage ? <p className="event-reg-done-resend-message" role="status">{resendMessage}</p> : null}
    </section>
  );
};
