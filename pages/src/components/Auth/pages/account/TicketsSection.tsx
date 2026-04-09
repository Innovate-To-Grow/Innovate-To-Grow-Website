import type {Registration} from '../../../../features/events/api';

interface TicketsSectionProps {
  tickets: Registration[];
  ticketsLoading: boolean;
  resendingId: string | null;
  onResendTicketEmail: (registrationId: string) => void;
}

const formatDate = (date: string) =>
  new Date(`${date}T00:00:00`).toLocaleDateString('en-US', {weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'});

export const TicketsSection = ({
  tickets,
  ticketsLoading,
  resendingId,
  onResendTicketEmail,
}: TicketsSectionProps) => (
  <div className="account-section">
    <h2 className="account-section-title">My Tickets</h2>
    {ticketsLoading ? (
      <p className="account-status-text">Loading tickets...</p>
    ) : tickets.length === 0 ? (
      <p className="account-status-text">No event tickets yet.</p>
    ) : (
      <div className="account-ticket-list">
        {tickets.map((ticket) => (
          <div key={ticket.id} className="account-ticket-card">
            <div className="account-ticket-name">{ticket.event.name}</div>
            <div className="account-ticket-detail"><strong>Date:</strong> {formatDate(ticket.event.date)}</div>
            <div className="account-ticket-detail"><strong>Location:</strong> {ticket.event.location}</div>
            <div className="account-ticket-detail"><strong>Ticket:</strong> {ticket.ticket.name}</div>
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
        ))}
      </div>
    )}
  </div>
);
