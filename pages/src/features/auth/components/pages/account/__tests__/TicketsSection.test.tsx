import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {TicketsSection} from '../TicketsSection';
import type {EventRegistrationSummary, Registration} from '@/features/events/api';

const registration = (overrides: Partial<Registration> = {}): Registration => ({
  id: 'registration-1',
  ticket_code: 'I2G-TEST',
  attendee_first_name: 'Ada',
  attendee_last_name: 'Lovelace',
  attendee_name: 'Ada Lovelace',
  attendee_email: 'ada@example.com',
  attendee_secondary_email: '',
  attendee_phone: '',
  phone_verified: false,
  phone_verification_required: false,
  attendee_organization: 'Acme',
  registered_at: '2026-05-01T12:00:00Z',
  ticket_email_sent_at: null,
  ticket_email_error: '',
  barcode_format: 'PDF417',
  barcode_image: 'data:image/png;base64,test',
  event: {
    id: 'event-spring',
    name: 'Spring Showcase',
    slug: 'spring-showcase',
    date: '2026-05-01',
    location: 'Campus',
    description: 'Spring event',
  },
  ticket: {id: 'ticket-spring', name: 'General Admission'},
  answers: [],
  ...overrides,
});

const openEvent = (overrides: Partial<EventRegistrationSummary> = {}): EventRegistrationSummary => ({
  id: 'event-fall',
  name: 'Fall Showcase',
  slug: 'fall-showcase',
  date: '2026-10-01',
  location: 'Conference Center',
  description: 'Fall event',
  registration: null,
  ...overrides,
});

describe('TicketsSection', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders existing registrations and multiple open registration links', () => {
    render(
      <MemoryRouter>
        <TicketsSection
          tickets={[registration()]}
          openEvents={[openEvent(), openEvent({id: 'event-winter', name: 'Winter Showcase', slug: 'winter-showcase'})]}
          ticketsLoading={false}
          registrationEventsLoading={false}
          resendingId={null}
          onResendTicketEmail={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText('Spring Showcase')).toBeInTheDocument();
    expect(screen.getByText('Fall Showcase')).toBeInTheDocument();
    expect(screen.getByText('Winter Showcase')).toBeInTheDocument();
    expect(screen.getAllByRole('link', {name: 'Register for this event'})[0]).toHaveAttribute(
      'href',
      '/event-registration?event=fall-showcase',
    );
  });

  it('renders date ranges for both ticket and open-event cards', () => {
    const crossYearRegistration = registration({
      event: {
        id: 'event-spring',
        name: 'Year End Showcase',
        slug: 'year-end-showcase',
        date: '2026-12-31',
        end_date: '2027-01-02',
        location: 'Campus',
        description: 'Year end event',
      },
    });

    render(
      <MemoryRouter>
        <TicketsSection
          tickets={[crossYearRegistration]}
          openEvents={[openEvent({date: '2026-05-30', end_date: '2026-06-02'})]}
          ticketsLoading={false}
          registrationEventsLoading={false}
          resendingId={null}
          onResendTicketEmail={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText('Thursday, December 31, 2026 – Saturday, January 2, 2027')).toBeInTheDocument();
    expect(screen.getByText('Saturday, May 30 – Tuesday, June 2, 2026')).toBeInTheDocument();
  });

  it('renders an open-event registration missing from my-tickets as a ticket card', () => {
    const fallRegistration = registration({
      id: 'registration-fall',
      ticket_code: 'I2G-FALL',
      event: {
        id: 'event-fall',
        name: 'Fall Showcase',
        slug: 'fall-showcase',
        date: '2026-10-01',
        location: 'Conference Center',
        description: 'Fall event',
      },
    });

    render(
      <MemoryRouter>
        <TicketsSection
          tickets={[]}
          openEvents={[openEvent({registration: fallRegistration})]}
          ticketsLoading={false}
          registrationEventsLoading={false}
          resendingId={null}
          onResendTicketEmail={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText('I2G-FALL')).toBeInTheDocument();
    expect(screen.queryByRole('link', {name: 'Register for this event'})).not.toBeInTheDocument();
  });

  it('deduplicates a registration present in both tickets and the open-events feed', () => {
    const fallRegistration = registration({
      id: 'registration-fall',
      ticket_code: 'I2G-FALL',
      event: {
        id: 'event-fall',
        name: 'Fall Showcase',
        slug: 'fall-showcase',
        date: '2026-10-01',
        location: 'Conference Center',
        description: 'Fall event',
      },
    });

    render(
      <MemoryRouter>
        <TicketsSection
          tickets={[fallRegistration]}
          openEvents={[openEvent({registration: fallRegistration})]}
          ticketsLoading={false}
          registrationEventsLoading={false}
          resendingId={null}
          onResendTicketEmail={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getAllByText('I2G-FALL')).toHaveLength(1);
    expect(screen.queryByRole('link', {name: 'Register for this event'})).not.toBeInTheDocument();
  });

  it('shows the loading state while either feed is loading', () => {
    render(
      <MemoryRouter>
        <TicketsSection
          tickets={[]}
          openEvents={[]}
          ticketsLoading={false}
          registrationEventsLoading={true}
          resendingId={null}
          onResendTicketEmail={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText('Loading registrations...')).toBeInTheDocument();
  });

  it('shows the empty state when both feeds are empty', () => {
    render(
      <MemoryRouter>
        <TicketsSection
          tickets={[]}
          openEvents={[]}
          ticketsLoading={false}
          registrationEventsLoading={false}
          resendingId={null}
          onResendTicketEmail={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(
      screen.getByText('No open registrations right now, and no past event registrations on this account.'),
    ).toBeInTheDocument();
  });
});
