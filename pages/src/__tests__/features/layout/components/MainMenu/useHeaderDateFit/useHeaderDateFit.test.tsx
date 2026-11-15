import {cleanup} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {measureDateHidden} from '@/features/layout/components/MainMenu/useHeaderDateFit';
import {
  computedStyles,
  expectFitsFrom,
  FITS_EXACTLY_PX,
  type LabelBox,
  makeHeader,
  stubComputedStyles,
} from '@/__tests__/features/layout/components/MainMenu/useHeaderDateFit/headerDateFitFixtures';

afterEach(() => {
  cleanup();
  computedStyles.clear();
  Reflect.deleteProperty(document, 'fonts');
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('measureDateHidden', () => {
  it('shows the date when it fits beside the menu and the member link, and hides it one pixel short', () => {
    stubComputedStyles();
    expect(measureDateHidden(makeHeader({rowWidth: FITS_EXACTLY_PX}).header)).toBe(false);
    expect(measureDateHidden(makeHeader({rowWidth: FITS_EXACTLY_PX - 1}).header)).toBe(true);
  });

  describe('the member label', () => {
    const withLabel = (label: LabelBox) => ({member: {width: 150, paddingLeft: '12px', label}});

    it('without a max-width, counts all of it that the ellipsis cuts off', () => {
      stubComputedStyles();
      expectFitsFrom(FITS_EXACTLY_PX + 30, withLabel({scrollWidth: 120, clientWidth: 90}));
      expectFitsFrom(FITS_EXACTLY_PX + 100, withLabel({scrollWidth: 300, clientWidth: 200, maxWidth: 'none'}));
      // A max-width that does not parse caps nothing either.
      expectFitsFrom(FITS_EXACTLY_PX + 100, withLabel({scrollWidth: 300, clientWidth: 200, maxWidth: ''}));
    });

    it('adds nothing for a label longer than its 16rem cap when the row squeezes nothing', () => {
      stubComputedStyles();
      // 16rem = 256px: the label stops at its cap whatever the room, so more room would not show more of it.
      expectFitsFrom(FITS_EXACTLY_PX, withLabel({scrollWidth: 300, clientWidth: 256, maxWidth: '256px'}));
    });

    it('adds only up to the cap for a capped label that the row squeezes', () => {
      stubComputedStyles();
      // Squeezed to 200px: room would bring it back to 256px (56px more), not to its full 300px.
      expectFitsFrom(FITS_EXACTLY_PX + 56, withLabel({scrollWidth: 300, clientWidth: 200, maxWidth: '256px'}));
    });

    it('adds nothing for a label shorter than its box', () => {
      stubComputedStyles();
      expectFitsFrom(FITS_EXACTLY_PX, withLabel({scrollWidth: 60, clientWidth: 90}));
    });
  });

  it("leaves out the member's current divider padding, so a shown and a hidden date give one answer", () => {
    stubComputedStyles();
    // Next to a hidden date the member link has no divider padding and is 12px narrower.
    expectFitsFrom(FITS_EXACTLY_PX, {member: {width: 138, paddingLeft: '0px', label: {scrollWidth: 90, clientWidth: 90}}});
  });

  it("adds the fixed 12px gap and 12px divider to the date's own width", () => {
    stubComputedStyles();
    // A bare row: no padding, gaps, margin, logo slot, menu items or member link; a 100px date needs 124px
    // (+1 slack).
    const bare = {
      rowPadding: 0,
      columnGap: 'normal',
      utilityMarginRight: '0px',
      logoSlot: '',
      menuItemWidths: [],
      member: null,
      dateWidth: 100,
    };
    expectFitsFrom(125, bare);
    // A member link without a label element counts with its box alone.
    expectFitsFrom(175, {...bare, member: {width: 50, paddingLeft: '0px'}});
  });

  it("reads --itg-menu-logo-slot from the header's computed style", () => {
    const getComputedStyle = stubComputedStyles();
    const {header} = makeHeader({rowWidth: FITS_EXACTLY_PX, logoSlot: '60px'});

    // 12px more than the default slot: the same row is now short.
    expect(measureDateHidden(header)).toBe(true);
    expect(getComputedStyle).toHaveBeenCalledWith(header);
    expectFitsFrom(FITS_EXACTLY_PX + 12, {logoSlot: '60px'});
  });

  it('returns null when the row has no layout to measure', () => {
    stubComputedStyles();
    expect(measureDateHidden(makeHeader({rowWidth: 0}).header)).toBeNull();
    // Nothing left inside the 20px + 20px padding.
    expect(measureDateHidden(makeHeader({rowWidth: 40}).header)).toBeNull();
    expect(measureDateHidden(makeHeader({rowWidth: 41}).header)).toBe(true);
  });

  it('returns null while the menu is the loading skeleton, however the row would come out', () => {
    stubComputedStyles();
    expect(measureDateHidden(makeHeader({skeleton: true, rowWidth: FITS_EXACTLY_PX - 1}).header)).toBeNull();
    expect(measureDateHidden(makeHeader({skeleton: true, rowWidth: 2000}).header)).toBeNull();
  });

  it.each([
    ['the menu row', 'site-header-menu-inner'],
    ['the menu list', 'menu-bar-list'],
    ['the utility', 'site-header-utility'],
    ['the date', 'site-header-date'],
  ])('returns null without %s', (_part, className) => {
    stubComputedStyles();
    const {header} = makeHeader();
    header.querySelector(`.${className}`)?.classList.remove(className);
    expect(measureDateHidden(header)).toBeNull();
  });
});
