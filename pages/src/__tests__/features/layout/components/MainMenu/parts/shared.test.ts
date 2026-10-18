import {describe, expect, it} from 'vitest';

import {formatMenuDate, memberDisplayName} from '@/features/layout/components/MainMenu/parts/shared';

describe('formatMenuDate', () => {
  it('formats the menu-row date as "Weekday D Month YYYY" with an ISO date', () => {
    expect(formatMenuDate(new Date(2026, 8, 20, 23, 59))).toEqual({
      label: 'Sunday 20 September 2026',
      iso: '2026-09-20',
    });
  });

  it('pads the ISO month and day', () => {
    expect(formatMenuDate(new Date(2027, 0, 5))).toEqual({label: 'Tuesday 5 January 2027', iso: '2027-01-05'});
  });
});

describe('memberDisplayName', () => {
  const format = (phone: string) => `fmt:${phone}`;

  it('prefers the email, then the formatted phone, then "Member"', () => {
    expect(memberDisplayName({email: 'a@b.c', phone: '+1'}, format)).toBe('a@b.c');
    expect(memberDisplayName({email: '', phone: '+1'}, format)).toBe('fmt:+1');
    expect(memberDisplayName(null, () => '')).toBe('Member');
  });
});
