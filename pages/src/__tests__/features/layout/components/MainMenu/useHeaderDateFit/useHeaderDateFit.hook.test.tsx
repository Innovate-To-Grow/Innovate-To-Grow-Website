import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {useHeaderDateHidden} from '@/features/layout/components/MainMenu/useHeaderDateFit';
import {
  collectFrames,
  computedStyles,
  FITS_EXACTLY_PX,
  flushMicrotasks,
  installResizeObserverStub,
  make,
  makeHeader,
  setViewportWidth,
  setWidth,
  stubComputedStyles,
} from '@/__tests__/features/layout/components/MainMenu/useHeaderDateFit/headerDateFitFixtures';

afterEach(() => {
  cleanup();
  computedStyles.clear();
  Reflect.deleteProperty(document, 'fonts');
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('useHeaderDateHidden', () => {
  it('gives its first answer before paint, without waiting for a frame', () => {
    stubComputedStyles();
    installResizeObserverStub();
    const frames = collectFrames();

    // The measurement overrides the viewport-width guess either way.
    const viewport = setViewportWidth(1400);
    const tooNarrow = makeHeader({rowWidth: FITS_EXACTLY_PX - 1});
    expect(renderHook(() => useHeaderDateHidden(tooNarrow.ref)).result.current).toBe(true);
    viewport.mockReturnValue(1024);
    const wide = makeHeader({rowWidth: FITS_EXACTLY_PX});
    expect(renderHook(() => useHeaderDateHidden(wide.ref)).result.current).toBe(false);
    expect(frames).toHaveLength(0);
  });

  describe('first guess, kept until a real measurement', () => {
    it.each([
      [1199, true],
      [1200, false],
      [1201, false],
    ])('at a %ipx viewport hides the date: %s', (viewportWidth, hidden) => {
      stubComputedStyles();
      installResizeObserverStub();
      collectFrames();
      setViewportWidth(viewportWidth);

      // The phone header: the row is not shown, so it has no width to measure.
      expect(renderHook(() => useHeaderDateHidden(makeHeader({rowWidth: 0}).ref)).result.current).toBe(hidden);
      // No header mounted at all.
      expect(renderHook(() => useHeaderDateHidden({current: null})).result.current).toBe(hidden);
    });

    it('stands while the menu is loading and gives way once the real list renders', async () => {
      stubComputedStyles();
      installResizeObserverStub();
      const frames = collectFrames();
      // Below 1200px the guess hides the date. The short skeleton would leave room for it, but is not measured.
      setViewportWidth(1024);
      const row = makeHeader({skeleton: true, menuItemWidths: [56, 72], rowWidth: FITS_EXACTLY_PX});
      const {result} = renderHook(() => useHeaderDateHidden(row.ref));
      expect(result.current).toBe(true);

      // Still loading: a skeleton row changes, and the frame it leads to keeps the guess.
      setWidth(make('li', 'menu-bar-item menu-bar-item--skeleton', row.list), 64);
      await flushMicrotasks();
      expect(frames).toHaveLength(1);
      act(() => frames[0](0));
      expect(result.current).toBe(true);

      // The items arrive: the real list replaces the skeleton, and the next frame decides (it fits).
      const list = make('ul', 'menu-bar-list');
      for (const width of [100, 120, 80]) setWidth(make('li', 'menu-bar-item', list), width);
      row.list.replaceWith(list);
      await flushMicrotasks();
      expect(result.current).toBe(true);
      expect(frames).toHaveLength(2);
      act(() => frames[1](0));
      expect(result.current).toBe(false);
    });
  });
});
