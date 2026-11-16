import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {SchedulePage} from '@/routes/SchedulePage/schedule/SchedulePage';
import {schedulePayload} from '@/__tests__/routes/SchedulePage/schedule/schedulePageFixtures';

const useCurrentEventScheduleMock = vi.fn();

vi.mock('@/features/events/hooks/useCurrentEventSchedule', () => ({
  useCurrentEventSchedule: (scheduleId?: string | null) => useCurrentEventScheduleMock(scheduleId),
}));

describe('SchedulePage', () => {
  beforeEach(() => {
    useCurrentEventScheduleMock.mockReset();
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: 1024,
    });
    // jsdom does not implement scrollIntoView or matchMedia.
    Element.prototype.scrollIntoView = vi.fn();
    delete (window as {matchMedia?: unknown}).matchMedia;
  });

  afterEach(() => {
    cleanup();
  });

  it('renders full missing presentation rows as Break while leaving partial missing cells blank', () => {
    useCurrentEventScheduleMock.mockReturnValue({
      data: schedulePayload(),
      loading: false,
      error: null,
    });

    const {container} = render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    const rows = container.querySelectorAll('tbody tr');

    expect(container.querySelectorAll('.schedule-presentation-break')).toHaveLength(4);
    expect(rows[0]).toHaveTextContent('CSE-101');
    expect(rows[0]).toHaveTextContent('CSE-201');
    expect(rows[1]).toHaveTextContent('Break');
    expect(rows[2]).toHaveTextContent('CSE-103');
    expect(rows[2]).not.toHaveTextContent('TBD');
    expect(rows[3]?.querySelectorAll('.schedule-presentation-break')).toHaveLength(2);
    expect(rows[3]).toHaveTextContent('Break');
    expect(rows[3]).not.toHaveTextContent('TBD');
  });

  it('uses the same missing slot rendering rules in the mobile schedule cards', () => {
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: 500,
    });
    useCurrentEventScheduleMock.mockReturnValue({
      data: schedulePayload(),
      loading: false,
      error: null,
    });

    const {container} = render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    const cards = container.querySelectorAll('.schedule-mobile-card');

    expect(container.querySelectorAll('.schedule-mobile-break')).toHaveLength(4);
    expect(cards[0]).toHaveTextContent('CSE-103');
    expect(cards[1]).not.toHaveTextContent('2:00TBD');
    expect(cards[0]).toHaveTextContent('2:30Break');
    expect(cards[1]).toHaveTextContent('2:30Break');
  });

  it('passes an explicit schedule id into the schedule hook', () => {
    useCurrentEventScheduleMock.mockReturnValue({
      data: schedulePayload(),
      loading: false,
      error: null,
    });

    render(
      <MemoryRouter>
        <SchedulePage scheduleId="schedule-123" />
      </MemoryRouter>,
    );

    expect(useCurrentEventScheduleMock).toHaveBeenCalledWith('schedule-123');
  });

  it('treats an explicit null prop as authoritative and ignores the URL', () => {
    // The embed page resolves block > widget > active itself; a null prop means
    // "active schedule", so a stray ?schedule_id= on the iframe URL must not win.
    useCurrentEventScheduleMock.mockReturnValue({
      data: schedulePayload(),
      loading: false,
      error: null,
    });

    render(
      <MemoryRouter initialEntries={['/_embed/schedule-widget?schedule_id=not-a-uuid']}>
        <SchedulePage scheduleId={null} />
      </MemoryRouter>,
    );

    expect(useCurrentEventScheduleMock).toHaveBeenCalledWith(null);
  });

  it('uses schedule_id from the URL when no prop is provided', () => {
    useCurrentEventScheduleMock.mockReturnValue({
      data: schedulePayload(),
      loading: false,
      error: null,
    });

    render(
      <MemoryRouter initialEntries={['/schedule?schedule_id=schedule-query']}>
        <SchedulePage />
      </MemoryRouter>,
    );

    expect(useCurrentEventScheduleMock).toHaveBeenCalledWith('schedule-query');
  });

  it('renders the loading state as the shared loading indicator', () => {
    useCurrentEventScheduleMock.mockReturnValue({data: null, loading: true, error: null});

    render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    // The same ring and label as the event archive's schedule box (ScheduleGrid), inside the status line.
    const label = screen.getByText('Loading schedule…');
    expect(label).toHaveClass('loading-indicator-label');
    expect(label.childNodes).toHaveLength(1);
    const status = screen.getByRole('status');
    expect(status).toHaveClass('schedule-page-state', 'schedule-page-state-loading');
    expect(status).toHaveTextContent('Loading schedule…');
    expect(status.querySelector('.loading-indicator-spinner')).toHaveAttribute('aria-hidden', 'true');
  });

  it('renders the error state and its unavailable fallback', () => {
    useCurrentEventScheduleMock.mockReturnValue({data: null, loading: false, error: 'Backend unavailable'});

    render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Backend unavailable')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Backend unavailable');
  });
});
