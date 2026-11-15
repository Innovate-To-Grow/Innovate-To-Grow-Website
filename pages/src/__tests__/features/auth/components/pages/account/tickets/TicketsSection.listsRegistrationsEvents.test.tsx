import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {TicketsSection} from '@/features/auth/components/pages/account/tickets/TicketsSection';
import {registration} from '@/__tests__/features/auth/components/pages/account/tickets/ticketsSectionFixtures';

describe('TicketsSection', () => {
  beforeEach(() => {
    // Before every event in the fixtures, so they all count as upcoming unless a test says otherwise.
    vi.useFakeTimers({toFake: ['Date']});
    vi.setSystemTime(new Date(2026, 3, 15, 12));
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('lists registrations for events that are over as past, without a barcode or resend button', () => {
    vi.setSystemTime(new Date(2026, 9, 19, 12));
    const upcoming = registration({
      id: 'registration-fall',
      ticket_code: 'I2G-FALL',
      event: {
        id: 'event-fall',
        name: 'Fall Showcase',
        slug: 'fall-showcase',
        date: '2026-12-11',
        location: 'Conference Center',
        description: 'Fall event',
      },
    });

    render(
      <MemoryRouter>
        <TicketsSection
          tickets={[registration(), upcoming]}
          openEvents={[]}
          ticketsLoading={false}
          registrationEventsLoading={false}
          resendingId={null}
          onResendTicketEmail={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', {name: 'Past Events'})).toBeInTheDocument();
    const pastCard = screen.getByText('Spring Showcase').closest('.account-ticket-card') as HTMLElement;
    expect(within(pastCard).getByText('Past event')).toBeInTheDocument();
    expect(within(pastCard).queryByAltText('Ticket barcode')).not.toBeInTheDocument();
    expect(within(pastCard).queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByText('I2G-TEST')).not.toBeInTheDocument();

    expect(screen.getByText('I2G-FALL')).toBeInTheDocument();
    expect(screen.getAllByRole('button', {name: 'Resend Ticket Email'})).toHaveLength(1);
  });

  it('keeps a ticket upcoming through the last day of the event', () => {
    vi.setSystemTime(new Date(2026, 4, 2, 23, 30));
    render(
      <MemoryRouter>
        <TicketsSection
          tickets={[registration({event: {...registration().event, end_date: '2026-05-02'}})]}
          openEvents={[]}
          ticketsLoading={false}
          registrationEventsLoading={false}
          resendingId={null}
          onResendTicketEmail={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText('I2G-TEST')).toBeInTheDocument();
    expect(screen.queryByText('Past event')).not.toBeInTheDocument();
  });

  it('shows the barcode full screen on tap and closes it with Escape', () => {
    render(
      <MemoryRouter>
        <TicketsSection
          tickets={[registration()]}
          openEvents={[]}
          ticketsLoading={false}
          registrationEventsLoading={false}
          resendingId={null}
          onResendTicketEmail={vi.fn()}
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', {name: 'Show the ticket barcode full screen'}));
    const dialog = screen.getByRole('dialog', {name: 'Ticket barcode'});
    expect(within(dialog).getByAltText('Ticket barcode')).toHaveAttribute('src', 'data:image/png;base64,test');
    expect(within(dialog).getByRole('button', {name: 'Close'})).toHaveFocus();

    fireEvent.keyDown(document, {key: 'Escape'});
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
