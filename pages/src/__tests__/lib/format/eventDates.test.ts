import {describe, expect, it} from 'vitest';

import {formatEventDateRange, isEventPast} from '@/lib/format/eventDates';

describe('formatEventDateRange', () => {
  it('keeps old payloads without end_date as a single-day event', () => {
    expect(formatEventDateRange('2026-05-01')).toBe('Friday, May 1, 2026');
  });

  it('renders a same-day range only once', () => {
    expect(formatEventDateRange('2026-05-01', '2026-05-01')).toBe('Friday, May 1, 2026');
  });

  it('renders both endpoints for a same-month range', () => {
    expect(formatEventDateRange('2026-05-01', '2026-05-03')).toBe(
      'Friday, May 1 – Sunday, May 3, 2026',
    );
  });

  it('renders both months for a cross-month range', () => {
    expect(formatEventDateRange('2026-05-30', '2026-06-02')).toBe(
      'Saturday, May 30 – Tuesday, June 2, 2026',
    );
  });

  it('renders both years for a cross-year range', () => {
    expect(formatEventDateRange('2026-12-31', '2027-01-02')).toBe(
      'Thursday, December 31, 2026 – Saturday, January 2, 2027',
    );
  });
});

describe('isEventPast', () => {
  const now = new Date(2026, 9, 19, 9, 0);

  it('treats an event as past only after its last day', () => {
    expect(isEventPast('2026-10-18', null, now)).toBe(true);
    expect(isEventPast('2026-10-19', null, now)).toBe(false);
    expect(isEventPast('2026-12-11', undefined, now)).toBe(false);
  });

  it('uses the end date of a multi-day event', () => {
    expect(isEventPast('2026-10-17', '2026-10-19', now)).toBe(false);
    expect(isEventPast('2026-10-16', '2026-10-18', now)).toBe(true);
  });

  it('ignores the time part of ISO timestamps', () => {
    expect(isEventPast('2026-10-19T23:59:00Z', null, now)).toBe(false);
  });
});
