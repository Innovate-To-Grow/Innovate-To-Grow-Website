import {Link} from 'react-router-dom';
import type {EventRegistrationOptions, Registration} from '../../../../features/events/api';

interface TicketsSectionProps {
  tickets: Registration[];
  liveEvent: EventRegistrationOptions | null;
  ticketsLoading: boolean;
  liveEventLoading: boolean;
  resendingId: string | null;
  onResendTicketEmail: (registrationId: string) => void;
}

const formatDate = (date: string) =>
  new Date(`${date}T00:00:00`).toLocaleDateString('en-US', {weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'});

const RegistrationCard = ({
  ticket,
  resendingId,
  onResendTicketEmail,
}: {
  ticket: Registration;
  resendingId: string | null;
  onResendTicketEmail: (registrationId: string) => void;
}) => (
  <div className="account-ticket-card">
    <div className="account-ticket-name">{ticket.event.name}</div>
    <div className="account-ticket-detail">
      <strong>Date:</strong> {formatDate(ticket.event.date)}
    </div>
    <div className="account-ticket-detail">
      <strong>Location:</strong> {ticket.event.location}
    </div>
    <div className="account-ticket-detail">
      <strong>Ticket:</strong> {ticket.ticket.name}
    </div>
    <div className="account-ticket-code">{ticket.ticket_code}</div>
    <div className="account-ticket-barcode">
      <img src={ticket.barcode_image} alt="Ticket barcode" />
    </div>
    <div className="account-ticket-email-status">
      {ticket.ticket_email_sent_at
        ? `Email sent ${new Date(ticket.ticket_email_sent_at).toLocaleString()}`
        : ticket.ticket_email_error
          ? `Email failed: ${ticket.ticket_email_error}`
          : 'Email not sent'}
    </div>
    <button
      type="button"
      className="account-outline-btn"
      disabled={resendingId === ticket.id}
      onClick={() => onResendTicketEmail(ticket.id)}
    >
      {resendingId === ticket.id ? 'Sending...' : 'Resend Ticket Email'}
    </button>
  </div>
);

const OpenRegistrationCard = ({event}: {event: EventRegistrationOptions}) => {
  const location = event.location?.trim() ?? '';
  const description = event.description?.trim() ?? '';
  const showDescription = Boolean(description && description !== location);

  return (
    <div className="account-ticket-card account-open-registration-card">
      <div className="account-open-reg-header">
        <h3 className="account-open-reg-title">{event.name}</h3>
        <span className="account-open-reg-badge">Open</span>
      </div>
      <p className="account-open-reg-lead">You are not registered yet. Use the button below to complete registration.</p>
      <ul className="account-open-reg-details">
        <li>
          <span className="account-open-reg-detail-label">Date</span>
          <span className="account-open-reg-detail-value">{formatDate(event.date)}</span>
        </li>
        <li>
          <span className="account-open-reg-detail-label">Location</span>
          <span className="account-open-reg-detail-value">{location || '—'}</span>
        </li>
      </ul>
      {showDescription ? <p className="account-open-reg-description">{description}</p> : null}
      <div className="account-open-reg-actions">
        <Link to="/event-registration" className="account-edit-btn account-open-reg-cta">
          Register for this event
        </Link>
      </div>
    </div>
  );
};

export const TicketsSection = ({
  tickets,
  liveEvent,
  ticketsLoading,
  liveEventLoading,
  resendingId,
  onResendTicketEmail,
}: TicketsSectionProps) => {
  const loading = ticketsLoading || liveEventLoading;
  const liveEventId = liveEvent?.id ?? null;
  const liveRegistration: Registration | null =
    liveEventId != null
      ? tickets.find((t) => t.event.id === liveEventId) ?? liveEvent?.registration ?? null
      : null;
  const otherRegistrations = liveEventId != null ? tickets.filter((t) => t.event.id !== liveEventId) : tickets;
  const showOpenLiveEvent = liveEvent != null && liveRegistration == null;
  const hasRows = showOpenLiveEvent || liveRegistration != null || otherRegistrations.length > 0;

  return (
    <div className="account-section">
      <h2 className="account-section-title">Event Registrations</h2>
      {loading ? (
        <p className="account-status-text">Loading registrations...</p>
      ) : !hasRows ? (
        <p className="account-status-text">No open registrations right now, and no past event registrations on this account.</p>
      ) : (
        <div className="account-ticket-list">
          {showOpenLiveEvent ? <OpenRegistrationCard event={liveEvent} /> : null}
          {liveRegistration ? (
            <RegistrationCard
              ticket={liveRegistration}
              resendingId={resendingId}
              onResendTicketEmail={onResendTicketEmail}
            />
          ) : null}
          {otherRegistrations.map((ticket) => (
            <RegistrationCard
              key={ticket.id}
              ticket={ticket}
              resendingId={resendingId}
              onResendTicketEmail={onResendTicketEmail}
            />
          ))}
        </div>
      )}
    </div>
  );
};
