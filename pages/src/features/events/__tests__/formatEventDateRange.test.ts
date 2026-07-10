import {describe, expect, it} from 'vitest';

import {formatEventDateRange} from '../formatEventDateRange';

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
