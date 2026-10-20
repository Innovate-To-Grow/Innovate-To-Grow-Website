import {useEffect, useRef, useState} from 'react';
import {Link} from 'react-router';
import type {EventRegistrationSummary, Registration} from '@/features/events/api';
import {formatEventDateRange, isEventPast} from '@/features/events/formatEventDateRange';

interface TicketsSectionProps {
  tickets: Registration[];
  openEvents: EventRegistrationSummary[];
  ticketsLoading: boolean;
  registrationEventsLoading: boolean;
  resendingId: string | null;
  onResendTicketEmail: (registrationId: string) => void;
}

/** The ticket barcode at full screen width, so a door scanner can read it off a phone. */
const BarcodeOverlay = ({src, onClose}: {src: string; onClose: () => void}) => {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div className="account-ticket-barcode-overlay" role="dialog" aria-modal="true" aria-label="Ticket barcode" onClick={onClose}>
      <img src={src} alt="Ticket barcode" />
      <button ref={closeRef} type="button" className="itg-btn itg-btn-outline" onClick={onClose}>
        Close
      </button>
    </div>
  );
};

const RegistrationCard = ({
  ticket,
  resendingId,
  onResendTicketEmail,
}: {
  ticket: Registration;
  resendingId: string | null;
  onResendTicketEmail: (registrationId: string) => void;
}) => {
  const [barcodeExpanded, setBarcodeExpanded] = useState(false);

  return (
    <div className="account-ticket-card">
      <div className="account-ticket-name">{ticket.event.name}</div>
      <div className="account-ticket-detail">
        <strong>Date:</strong> {formatEventDateRange(ticket.event.date, ticket.event.end_date)}
      </div>
      <div className="account-ticket-detail">
        <strong>Location:</strong> {ticket.event.location}
      </div>
      <div className="account-ticket-detail">
        <strong>Ticket:</strong> {ticket.ticket.name}
      </div>
      <div className="account-ticket-code">{ticket.ticket_code}</div>
      <button
        type="button"
        className="account-ticket-barcode"
        aria-label="Show the ticket barcode full screen"
        onClick={() => setBarcodeExpanded(true)}
      >
        <img src={ticket.barcode_image} alt="Ticket barcode" />
        <span className="account-ticket-barcode-hint" aria-hidden="true">Tap to enlarge</span>
      </button>
      {barcodeExpanded ? <BarcodeOverlay src={ticket.barcode_image} onClose={() => setBarcodeExpanded(false)} /> : null}
      <div className="account-ticket-email-status">
        {ticket.ticket_email_sent_at
          ? `Email sent ${new Date(ticket.ticket_email_sent_at).toLocaleString()}`
          : ticket.ticket_email_error
            ? `Email failed: ${ticket.ticket_email_error}`
            : 'Email not sent'}
      </div>
      <button
        type="button"
        className="itg-btn itg-btn-outline account-outline-btn"
        disabled={resendingId === ticket.id}
        onClick={() => onResendTicketEmail(ticket.id)}
      >
        {resendingId === ticket.id ? 'Sending...' : 'Resend Ticket Email'}
      </button>
    </div>
  );
};

/** A registration for an event that is over: a record, with no barcode to present or email to resend. */
const PastRegistrationCard = ({ticket}: {ticket: Registration}) => (
  <div className="account-ticket-card account-ticket-card--past">
    <div className="account-open-reg-header">
      <div className="account-ticket-name">{ticket.event.name}</div>
      <span className="itg-tag account-ticket-past-badge">Past event</span>
    </div>
    <div className="account-ticket-detail">
      <strong>Date:</strong> {formatEventDateRange(ticket.event.date, ticket.event.end_date)}
    </div>
    <div className="account-ticket-detail">
      <strong>Location:</strong> {ticket.event.location}
    </div>
    <div className="account-ticket-detail">
      <strong>Ticket:</strong> {ticket.ticket.name}
    </div>
  </div>
);

const OpenRegistrationCard = ({event}: {event: EventRegistrationSummary}) => {
  const location = event.location?.trim() ?? '';
  const description = event.description?.trim() ?? '';
  const showDescription = Boolean(description && description !== location);

  return (
    <div className="account-ticket-card account-open-registration-card">
      <div className="account-open-reg-header">
        <h3 className="account-open-reg-title">{event.name}</h3>
        <span className="itg-tag itg-tag-new account-open-reg-badge">Open</span>
      </div>
      <p className="account-open-reg-lead">You are not registered yet. Use the button below to complete registration.</p>
      <ul className="account-open-reg-details">
        <li>
          <span className="account-open-reg-detail-label">Date</span>
          <span className="account-open-reg-detail-value">{formatEventDateRange(event.date, event.end_date)}</span>
        </li>
        <li>
          <span className="account-open-reg-detail-label">Location</span>
          <span className="account-open-reg-detail-value">{location || '—'}</span>
        </li>
      </ul>
      {showDescription ? <p className="account-open-reg-description">{description}</p> : null}
      <div className="account-open-reg-actions">
        <Link to={`/event-registration?event=${encodeURIComponent(event.slug)}`} className="itg-btn itg-btn-outline account-open-reg-cta">
          Register for this event
        </Link>
      </div>
    </div>
  );
};

export const TicketsSection = ({
  tickets,
  openEvents,
  ticketsLoading,
  registrationEventsLoading,
  resendingId,
  onResendTicketEmail,
}: TicketsSectionProps) => {
  const loading = ticketsLoading || registrationEventsLoading;
  const registrationsByEventId = new Map(tickets.map((ticket) => [ticket.event.id, ticket]));
  const openUnregisteredEvents = openEvents.filter((event) => !registrationsByEventId.has(event.id) && !event.registration);
  const ticketIds = new Set(tickets.map((ticket) => ticket.id));
  const openEventRegistrations = openEvents
    .map((event) => event.registration)
    .filter((registration): registration is Registration => registration !== null && !ticketIds.has(registration.id));
  const allRegistrations = [...tickets, ...openEventRegistrations];
  const upcomingRegistrations = allRegistrations.filter((ticket) => !isEventPast(ticket.event.date, ticket.event.end_date));
  const pastRegistrations = allRegistrations.filter((ticket) => isEventPast(ticket.event.date, ticket.event.end_date));
  const hasRows = openUnregisteredEvents.length > 0 || allRegistrations.length > 0;

  return (
    <div className="itg-panel account-section">
      <h2 className="account-section-title">Event Registrations</h2>
      {loading ? (
        <p className="account-status-text">Loading registrations...</p>
      ) : !hasRows ? (
        <p className="account-status-text">No open registrations right now, and no past event registrations on this account.</p>
      ) : (
        <div className="account-ticket-list">
          {openUnregisteredEvents.map((event) => (
            <OpenRegistrationCard key={event.id} event={event} />
          ))}
          {upcomingRegistrations.map((ticket) => (
            <RegistrationCard
              key={ticket.id}
              ticket={ticket}
              resendingId={resendingId}
              onResendTicketEmail={onResendTicketEmail}
            />
          ))}
          {pastRegistrations.length > 0 ? (
            <>
              <h3 className="account-subsection-title account-ticket-past-title">Past Events</h3>
              {pastRegistrations.map((ticket) => (
                <PastRegistrationCard key={ticket.id} ticket={ticket} />
              ))}
            </>
          ) : null}
        </div>
      )}
    </div>
  );
};
