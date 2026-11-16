import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {useHeaderDateHidden} from '@/features/layout/components/MainMenu/header/useHeaderDateFit';
import {
  collectFrames,
  computedStyles,
  FITS_EXACTLY_PX,
  flushMicrotasks,
  installFonts,
  installResizeObserverStub,
  make,
  makeHeader,
  ResizeObserverStub,
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
  it('turns ResizeObserver notifications into one re-measurement on the next frame', () => {
    stubComputedStyles();
    installResizeObserverStub();
    const frames = collectFrames();
    const row = makeHeader();
    const {result} = renderHook(() => useHeaderDateHidden(row.ref));
    const [observer] = ResizeObserverStub.instances;
    expect(observer.observed).toEqual([row.inner]);
    expect(result.current).toBe(false);

    // The row narrows: nothing is set inside the callback.
    row.setRowWidth(700);
    observer.notify();
    observer.notify();
    expect(result.current).toBe(false);
    expect(frames).toHaveLength(1);

    act(() => frames[0](0));
    expect(result.current).toBe(true);

    // Once the frame has run, the next notification asks for a new one.
    row.setRowWidth(900);
    observer.notify();
    expect(frames).toHaveLength(2);
    act(() => frames[1](0));
    expect(result.current).toBe(false);
  });

  it('re-measures on the next frame when the row content changes (menu items, member label)', async () => {
    stubComputedStyles();
    const observe = vi.spyOn(MutationObserver.prototype, 'observe');
    const frames = collectFrames();
    const row = makeHeader();
    const {result} = renderHook(() => useHeaderDateHidden(row.ref));
    expect(observe).toHaveBeenCalledWith(row.inner, {childList: true, subtree: true, characterData: true});

    // A menu item arrives and the member's label text changes, in the same task.
    setWidth(make('li', 'menu-bar-item', row.list), 60);
    (row.label?.firstChild as Text).data = 'someone.else@example.com';
    await flushMicrotasks();
    expect(result.current).toBe(false);
    expect(frames).toHaveLength(1);

    act(() => frames[0](0));
    expect(result.current).toBe(true);
  });

  it('re-measures on the next frame after window resizes and web fonts loading', async () => {
    stubComputedStyles();
    installResizeObserverStub();
    const {fonts, resolveReady} = installFonts();
    const frames = collectFrames();
    const row = makeHeader();
    const {result} = renderHook(() => useHeaderDateHidden(row.ref));

    // Every source within one frame shares that frame.
    row.setRowWidth(700);
    act(() => {
      window.dispatchEvent(new Event('resize'));
      window.dispatchEvent(new Event('resize'));
      fonts.dispatchEvent(new Event('loadingdone'));
      ResizeObserverStub.instances[0].notify();
    });
    expect(frames).toHaveLength(1);
    expect(result.current).toBe(false);
    act(() => frames[0](0));
    expect(result.current).toBe(true);

    row.setRowWidth(800);
    act(() => {
      fonts.dispatchEvent(new Event('loadingdone'));
    });
    expect(frames).toHaveLength(2);
    act(() => frames[1](0));
    expect(result.current).toBe(false);

    // document.fonts.ready settles once every font has loaded.
    row.setRowWidth(700);
    resolveReady();
    await flushMicrotasks();
    expect(frames).toHaveLength(3);
    expect(result.current).toBe(false);
    act(() => frames[2](0));
    expect(result.current).toBe(true);
  });

  it('keeps the previous answer when a measurement comes back null', async () => {
    stubComputedStyles();
    installResizeObserverStub();
    const frames = collectFrames();
    const narrow = makeHeader({rowWidth: FITS_EXACTLY_PX - 1});
    const hidden = renderHook(() => useHeaderDateHidden(narrow.ref));
    expect(hidden.result.current).toBe(true);

    // The phone header: the row is not shown, so it has no width.
    narrow.setRowWidth(0);
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    act(() => frames[0](0));
    expect(hidden.result.current).toBe(true);
    hidden.unmount();

    const wide = makeHeader();
    const shown = renderHook(() => useHeaderDateHidden(wide.ref));
    expect(shown.result.current).toBe(false);
    // A part goes missing mid-render.
    wide.date.remove();
    await flushMicrotasks();
    expect(frames).toHaveLength(2);
    act(() => frames[1](0));
    expect(shown.result.current).toBe(false);
  });
});
