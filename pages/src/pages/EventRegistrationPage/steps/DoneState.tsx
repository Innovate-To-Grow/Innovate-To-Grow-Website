import {Link} from 'react-router-dom';
import type {Registration} from '../../../features/events/api';
import {resendTicketEmail} from '../../../features/events/api';
import {formatEventDate} from './helpers';
import {useState} from 'react';

interface DoneStateProps {
  registration: Registration;
}

export const DoneState = ({registration}: DoneStateProps) => {
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
    <div className="event-reg-page">
      <div className="event-reg-done">
        <h2>You're Registered!</h2>
        <p className="event-reg-done-subtitle">
          Your ticket for <strong>{registration.event.name}</strong> is confirmed.
        </p>

        <img src={registration.barcode_image} alt="Ticket barcode" className="event-reg-barcode" />

        <div className="event-reg-ticket-code">{registration.ticket_code}</div>

        <div className="event-reg-done-details">
          <p><strong>Name:</strong> {registration.attendee_name}</p>
          <p><strong>Email:</strong> {registration.attendee_email}</p>
          <p><strong>Ticket:</strong> {registration.ticket.name}</p>
          <p><strong>Date:</strong> {formatEventDate(registration.event.date)}</p>
          <p><strong>Location:</strong> {registration.event.location}</p>
          {registration.event.description ? <p style={{marginTop: '0.75rem', fontSize: '0.9rem', color: '#4b5563', lineHeight: 1.5}}>{registration.event.description}</p> : null}
        </div>

        {registration.ticket_email_sent_at ? (
          <div className="event-reg-done-email-notice">
            A confirmation email was sent to {registration.attendee_email}
            {registration.attendee_secondary_email ? ` and ${registration.attendee_secondary_email}` : ''}.
          </div>
        ) : null}

        <div style={{display: 'flex', gap: '0.75rem', marginTop: '1rem', flexWrap: 'wrap'}}>
          <button
            type="button"
            className="event-reg-submit"
            style={{flex: 1}}
            onClick={handleResend}
            disabled={resending}
          >
            {resending ? 'Sending...' : 'Resend Confirmation Email'}
          </button>
          <Link to="/account" className="event-reg-submit" style={{flex: 1, textAlign: 'center', textDecoration: 'none'}}>
            View My Account
          </Link>
        </div>
        {resendMessage ? <p style={{marginTop: '0.5rem', fontSize: '0.85rem', color: '#6b7280', textAlign: 'center'}}>{resendMessage}</p> : null}
      </div>
    </div>
  );
};
