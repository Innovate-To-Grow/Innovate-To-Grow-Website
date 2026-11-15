import {act, cleanup, render, screen} from '@testing-library/react';
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

  it('colours each track column from its class tone family instead of inline palettes', () => {
    const payload = schedulePayload();
    payload.sections = [
      {...payload.sections[0], id: 's-cse', code: 'CSE'},
      {...payload.sections[0], id: 's-cap', code: 'CAP', label: 'Capstone', display_order: 2},
      {...payload.sections[0], id: 's-cee', code: 'CEE', label: 'Civil', display_order: 3},
      {...payload.sections[0], id: 's-zzz', code: 'ZZZ', label: 'Unknown', display_order: 4},
    ];
    useCurrentEventScheduleMock.mockReturnValue({data: payload, loading: false, error: null});

    const {container} = render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    const tables = container.querySelectorAll('.schedule-presentation-table');
    const firstSlotClass = (index: number) => tables[index].querySelector('.schedule-presentation-slot')?.className;
    // Known order: CAP, CEE, CSE, then unknown codes (which fall back to the gold family).
    expect(firstSlotClass(0)).toContain('schedule-tone--gold');
    expect(firstSlotClass(1)).toContain('schedule-tone--teal');
    expect(firstSlotClass(2)).toContain('schedule-tone--navy');
    expect(firstSlotClass(3)).toContain('schedule-tone--gold');
    // Second track column gets the next tone step.
    expect(tables[0].querySelectorAll('.schedule-presentation-topic-cell')[1].className).toContain('schedule-tone--col-1');
    expect(container.querySelector('.schedule-presentation-slot[style]')).toBeNull();
    // The time column is sized by the sheet; track columns share the rest.
    expect(tables[0].querySelector('col.schedule-presentation-time-col')).not.toBeNull();
    expect(container.querySelector('col[style]')).toBeNull();
  });

  it('tells each presentation grid its track count so the sheet can fit it to the main column', () => {
    const payload = schedulePayload();
    const [section] = payload.sections;
    const extraTracks = [3, 4, 5].map((trackNumber) => ({
      ...section.tracks[0],
      id: `track-${trackNumber}`,
      track_number: trackNumber,
      display_order: trackNumber,
    }));
    payload.sections = [
      {...section, id: 's-cse', code: 'CSE', tracks: [...section.tracks, ...extraTracks]},
      {...section, id: 's-cap', code: 'CAP', label: 'Capstone', display_order: 2},
    ];
    useCurrentEventScheduleMock.mockReturnValue({data: payload, loading: false, error: null});

    const {container} = render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    const cap = container.querySelector<HTMLTableElement>('.schedule-presentation-table--cap')!;
    const cse = container.querySelector<HTMLTableElement>('.schedule-presentation-table--cse')!;
    expect(cap.style.getPropertyValue('--schedule-track-count')).toBe('2');
    expect(cse.style.getPropertyValue('--schedule-track-count')).toBe('5');
    expect(cse.querySelectorAll('thead tr:nth-child(2) th')).toHaveLength(6);
  });

  it('shows the event description as the lede only when there is one', () => {
    const payload = schedulePayload();
    useCurrentEventScheduleMock.mockReturnValue({data: payload, loading: false, error: null});

    const {container, unmount} = render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );
    expect(screen.getByRole('heading', {name: 'Demo Day', level: 1})).toBeInTheDocument();
    expect(screen.getByText('May 7, 2026 · Conference Center')).toBeInTheDocument();
    expect(container.querySelector('.schedule-page-text')).toHaveTextContent('Presentation schedule');
    unmount();

    payload.event.description = '';
    const {container: emptyContainer} = render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );
    expect(emptyContainer.querySelector('.schedule-page-text')).toBeNull();
  });

  it('falls back to the unavailable message when there is neither data nor error', () => {
    useCurrentEventScheduleMock.mockReturnValue({data: null, loading: false, error: null});

    render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Event schedule is unavailable.')).toBeInTheDocument();
  });

  it('switches to the mobile grid when the media query fires', () => {
    const listeners = new Map<string, (event: {matches: boolean}) => void>();
    const mql = {
      matches: false,
      addEventListener: vi.fn((event: string, callback: (e: {matches: boolean}) => void) => {
        listeners.set(event, callback);
      }),
      removeEventListener: vi.fn(),
    };
    (window as unknown as {matchMedia: unknown}).matchMedia = vi.fn().mockReturnValue(mql);

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

    expect(container.querySelector('.schedule-presentation-table')).toBeInTheDocument();
    expect(container.querySelector('.schedule-page-mobile-grid')).not.toBeInTheDocument();

    act(() => {
      listeners.get('change')?.({matches: true});
    });

    expect(container.querySelector('.schedule-page-mobile-grid')).toBeInTheDocument();
    expect(container.querySelector('.schedule-presentation-table')).not.toBeInTheDocument();
  });

  it('sorts sections by known order, then display order, breaking ties by display order', () => {
    const payload = schedulePayload();
    const baseSection = payload.sections[0];
    payload.sections = [
      {...baseSection, id: 's-zzz', code: 'ZZZ', label: 'Unknown', display_order: 0},
      {...baseSection, id: 's-cap-a', code: 'CAP', label: 'Cap A', display_order: 5},
      {...baseSection, id: 's-cap-b', code: 'CAP', label: 'Cap B', display_order: 3},
    ];

    useCurrentEventScheduleMock.mockReturnValue({data: payload, loading: false, error: null});

    const {container} = render(
      <MemoryRouter>
        <SchedulePage />
      </MemoryRouter>,
    );

    const headings = container.querySelectorAll('.schedule-presentation-heading');
    expect([...headings].map((heading) => heading.textContent)).toEqual([
      'Cap B (CAP)',
      'Cap A (CAP)',
      'Unknown (ZZZ)',
    ]);
  });
});
