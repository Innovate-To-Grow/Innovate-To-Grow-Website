import {useEffect, useState} from 'react';
import {
  fetchMyTickets,
  fetchRegistrationEvents,
  resendTicketEmail,
  type EventRegistrationSummary,
  type Registration,
} from '@/features/events/api';

/** The member's event tickets and the events open for registration; both are non-critical. */
export function useAccountTickets(enabled: boolean) {
  const [tickets, setTickets] = useState<Registration[]>([]);
  const [ticketsLoading, setTicketsLoading] = useState(true);
  const [registrationEvents, setRegistrationEvents] = useState<EventRegistrationSummary[]>([]);
  const [registrationEventsLoading, setRegistrationEventsLoading] = useState(true);
  const [resendingId, setResendingId] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    const loadTickets = async () => {
      try {
        setTickets(await fetchMyTickets());
      } catch {
        // Non-critical.
      } finally {
        setTicketsLoading(false);
      }
    };
    void loadTickets();
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;
    const loadRegistrationEvents = async () => {
      try {
        setRegistrationEvents(await fetchRegistrationEvents());
      } catch {
        setRegistrationEvents([]);
      } finally {
        setRegistrationEventsLoading(false);
      }
    };
    void loadRegistrationEvents();
  }, [enabled]);

  const handleResendTicketEmail = async (registrationId: string) => {
    setResendingId(registrationId);
    try {
      await resendTicketEmail(registrationId);
      setTickets(await fetchMyTickets());
    } finally {
      setResendingId(null);
    }
  };

  return {tickets, ticketsLoading, registrationEvents, registrationEventsLoading, resendingId, handleResendTicketEmail};
}
