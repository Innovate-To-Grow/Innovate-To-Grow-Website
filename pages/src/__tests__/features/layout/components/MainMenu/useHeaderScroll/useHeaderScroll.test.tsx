import {cleanup} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  CONDENSE_HYSTERESIS_PX,
  nextCondensed,
} from '@/features/layout/components/MainMenu/header/useHeaderScroll';

const setScrollY = (value: number) => {
  Object.defineProperty(window, 'scrollY', {configurable: true, value});
};

const HEIGHT_PROPERTIES = ['--itg-header-bar-height', '--itg-header-menu-height'];

afterEach(() => {
  cleanup();
  setScrollY(0);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  for (const property of HEIGHT_PROPERTIES) document.documentElement.style.removeProperty(property);
});

describe('nextCondensed', () => {
  it('condenses once the bar has scrolled away, and lets go just before the row unpins', () => {
    expect(nextCondensed(false, 84, 85)).toBe(false);
    expect(nextCondensed(false, 85, 85)).toBe(true);
    expect(nextCondensed(true, 85 - CONDENSE_HYSTERESIS_PX, 85)).toBe(true);
    expect(nextCondensed(true, 85 - CONDENSE_HYSTERESIS_PX - 1, 85)).toBe(false);
    // Inside the hysteresis band the state depends on where it came from.
    expect(nextCondensed(false, 81, 85)).toBe(false);
    expect(nextCondensed(true, 81, 85)).toBe(true);
  });

  it('never condenses without a measured height', () => {
    expect(nextCondensed(false, 500, 0)).toBe(false);
    expect(nextCondensed(true, 500, Number.NaN)).toBe(false);
    expect(nextCondensed(true, 500, -5)).toBe(false);
  });
});
