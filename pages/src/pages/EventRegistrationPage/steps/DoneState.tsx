import {Link} from 'react-router-dom';
import type {Registration} from '../../../features/events/api';
import {formatEventDate} from './helpers';

interface DoneStateProps {
  registration: Registration;
}

export const DoneState = ({registration}: DoneStateProps) => (
  <div className="event-reg-page">
    <div className="event-reg-done">
      <h2>You're Registered!</h2>
      <p className="event-reg-done-subtitle">
        Your ticket for <strong>{registration.event.name}</strong> is confirmed.
      </p>

      <img src={registration.barcode_image} alt="Ticket barcode" className="event-reg-barcode" />

      <div className="event-reg-ticket-code">{registration.ticket_code}</div>

      <div className="event-reg-done-details">
        <p><strong>Ticket:</strong> {registration.ticket.name}</p>
        <p><strong>Date:</strong> {formatEventDate(registration.event.date)}</p>
        <p><strong>Location:</strong> {registration.event.location}</p>
      </div>

      {registration.ticket_email_sent_at ? (
        <div className="event-reg-done-email-notice">
          A confirmation email with your ticket has been sent to {registration.attendee_email}.
        </div>
      ) : registration.ticket_email_error ? (
        <div className="event-reg-done-email-error">
          We couldn't send the confirmation email. You can resend it from your account page.
        </div>
      ) : null}

      <Link to="/account" className="event-reg-link">
        View My Account
      </Link>
    </div>
  </div>
);
