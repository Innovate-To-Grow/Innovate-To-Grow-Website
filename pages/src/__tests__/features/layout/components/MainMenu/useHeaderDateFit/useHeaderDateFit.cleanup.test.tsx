import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {useHeaderDateHidden} from '@/features/layout/components/MainMenu/useHeaderDateFit';
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
  it('stops on unmount: observers disconnect, listeners go and a pending frame is cancelled', () => {
    stubComputedStyles();
    installResizeObserverStub();
    const {fonts} = installFonts();
    const disconnect = vi.spyOn(MutationObserver.prototype, 'disconnect');
    const addWindowListener = vi.spyOn(window, 'addEventListener');
    const removeWindowListener = vi.spyOn(window, 'removeEventListener');
    const addFontsListener = vi.spyOn(fonts, 'addEventListener');
    const removeFontsListener = vi.spyOn(fonts, 'removeEventListener');
    const cancel = vi.spyOn(window, 'cancelAnimationFrame');
    const frames = collectFrames();
    const row = makeHeader();
    const {unmount} = renderHook(() => useHeaderDateHidden(row.ref));

    const onResize = addWindowListener.mock.calls.find(([type]) => type === 'resize')?.[1];
    const onFontsLoaded = addFontsListener.mock.calls.find(([type]) => type === 'loadingdone')?.[1];
    expect(onResize).toEqual(expect.any(Function));
    expect(onFontsLoaded).toBe(onResize);

    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    expect(frames).toHaveLength(1);
    unmount();

    expect(ResizeObserverStub.instances[0].disconnected).toBe(true);
    expect(disconnect).toHaveBeenCalledTimes(1);
    expect(removeWindowListener).toHaveBeenCalledWith('resize', onResize);
    expect(removeFontsListener).toHaveBeenCalledWith('loadingdone', onFontsLoaded);
    expect(cancel).toHaveBeenCalledWith(1);
  });

  it('does not schedule anything for a fonts.ready that settles after unmount', async () => {
    stubComputedStyles();
    installResizeObserverStub();
    const {fonts, resolveReady} = installFonts();
    const cancel = vi.spyOn(window, 'cancelAnimationFrame');
    const frames = collectFrames();
    const row = makeHeader();
    const {unmount} = renderHook(() => useHeaderDateHidden(row.ref));

    // No frame is pending, so none is cancelled.
    unmount();
    expect(cancel).not.toHaveBeenCalled();

    resolveReady();
    await flushMicrotasks();
    window.dispatchEvent(new Event('resize'));
    fonts.dispatchEvent(new Event('loadingdone'));
    setWidth(make('li', 'menu-bar-item', row.list), 60);
    await flushMicrotasks();
    expect(frames).toHaveLength(0);
  });

  it('still measures and follows window resizes without observers or a font set API', () => {
    stubComputedStyles();
    vi.stubGlobal('ResizeObserver', undefined);
    vi.stubGlobal('MutationObserver', undefined);
    // A font set without the events or the ready promise.
    Object.defineProperty(document, 'fonts', {configurable: true, value: {}});
    const frames = collectFrames();
    const row = makeHeader();
    const {result, unmount} = renderHook(() => useHeaderDateHidden(row.ref));
    expect(result.current).toBe(false);

    row.setRowWidth(700);
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    act(() => frames[0](0));
    expect(result.current).toBe(true);
    expect(() => unmount()).not.toThrow();
  });

  it('works without document.fonts at all, as in jsdom', () => {
    stubComputedStyles();
    installResizeObserverStub();
    const frames = collectFrames();
    const row = makeHeader({rowWidth: FITS_EXACTLY_PX - 1});
    const {result, unmount} = renderHook(() => useHeaderDateHidden(row.ref));
    expect(result.current).toBe(true);
    expect(frames).toHaveLength(0);
    expect(() => unmount()).not.toThrow();
  });

  it('does nothing without a mounted header or menu row', () => {
    const getComputedStyle = stubComputedStyles();
    installResizeObserverStub();
    const frames = collectFrames();
    // A wide viewport: the first guess shows the date, and nothing ever changes it.
    setViewportWidth(1280);

    expect(renderHook(() => useHeaderDateHidden({current: null})).result.current).toBe(false);
    const bareHeader = document.createElement('header');
    expect(renderHook(() => useHeaderDateHidden({current: bareHeader})).result.current).toBe(false);

    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    expect(ResizeObserverStub.instances).toHaveLength(0);
    expect(frames).toHaveLength(0);
    expect(getComputedStyle).not.toHaveBeenCalled();
  });
});
