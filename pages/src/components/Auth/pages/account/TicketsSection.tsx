import type {Registration} from '../../../../features/events/api';

interface TicketsSectionProps {
  tickets: Registration[];
  ticketsLoading: boolean;
  resendingId: string | null;
  onResendTicketEmail: (registrationId: string) => void;
}

const formatDate = (date: string) =>
  new Date(`${date}T00:00:00`).toLocaleDateString('en-US', {year: 'numeric', month: 'long', day: 'numeric'});

export const TicketsSection = ({
  tickets,
  ticketsLoading,
  resendingId,
  onResendTicketEmail,
}: TicketsSectionProps) => (
  <div className="account-section">
    <h2 className="account-section-title">My Tickets</h2>
    {ticketsLoading ? (
      <p style={{color: '#6b7280', fontSize: '0.9rem'}}>Loading tickets...</p>
    ) : tickets.length === 0 ? (
      <p style={{color: '#6b7280', fontSize: '0.9rem'}}>No event tickets yet.</p>
    ) : (
      <div style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
        {tickets.map((ticket) => (
          <div key={ticket.id} style={{padding: '1rem', borderRadius: '10px', background: '#f8fafc', border: '1px solid #dbe3ef'}}>
            <div style={{fontWeight: 700, color: '#003366', marginBottom: '0.5rem'}}>{ticket.event.name}</div>
            <div style={{fontSize: '0.85rem', color: '#374151', marginBottom: '0.25rem'}}><strong>Date:</strong> {formatDate(ticket.event.date)}</div>
            <div style={{fontSize: '0.85rem', color: '#374151', marginBottom: '0.25rem'}}><strong>Location:</strong> {ticket.event.location}</div>
            <div style={{fontSize: '0.85rem', color: '#374151', marginBottom: '0.25rem'}}><strong>Ticket:</strong> {ticket.ticket.name}</div>
            <div style={{fontSize: '1.1rem', fontWeight: 700, color: '#003366', margin: '0.5rem 0', letterSpacing: '0.04em'}}>{ticket.ticket_code}</div>
            <div style={{textAlign: 'center', margin: '0.75rem 0'}}>
              <img src={ticket.barcode_image} alt="Ticket barcode" style={{maxWidth: '100%', borderRadius: '6px', border: '1px solid #e5e7eb', padding: '8px', background: '#fff'}} />
            </div>
            <div style={{fontSize: '0.8rem', color: '#6b7280', marginBottom: '0.5rem'}}>
              {ticket.ticket_email_sent_at
                ? `Email sent ${new Date(ticket.ticket_email_sent_at).toLocaleString()}`
                : ticket.ticket_email_error
                  ? `Email failed: ${ticket.ticket_email_error}`
                  : 'Email not sent'}
            </div>
            <button
              type="button"
              className="account-edit-btn"
              style={{fontSize: '0.8rem', padding: '0.4rem 0.8rem'}}
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
