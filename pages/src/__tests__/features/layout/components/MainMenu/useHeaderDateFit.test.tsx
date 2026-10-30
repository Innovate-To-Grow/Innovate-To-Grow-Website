import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {measureDateHidden, useHeaderDateHidden} from '@/features/layout/components/MainMenu/useHeaderDateFit';

/** What getComputedStyle reports for one element; anything unset reads as the browser's default. */
interface FakeStyle {
  paddingLeft?: string;
  paddingRight?: string;
  columnGap?: string;
  marginRight?: string;
  maxWidth?: string;
  vars?: Record<string, string>;
}

const computedStyles = new Map<Element, FakeStyle>();

const stubComputedStyles = () =>
  vi.spyOn(window, 'getComputedStyle').mockImplementation((element: Element) => {
    const {vars = {}, ...style} = computedStyles.get(element) ?? {};
    return {
      paddingLeft: '0px',
      paddingRight: '0px',
      columnGap: 'normal',
      marginRight: '0px',
      maxWidth: 'none',
      ...style,
      getPropertyValue: (name: string) => vars[name] ?? '',
    } as unknown as CSSStyleDeclaration;
  });

const setWidth = (element: HTMLElement, width: number) => {
  element.getBoundingClientRect = () =>
    ({width, height: 0, top: 0, left: 0, right: width, bottom: 0, x: 0, y: 0, toJSON: () => ({})}) as DOMRect;
};

const setBoxWidths = (element: HTMLElement, widths: {clientWidth?: number; scrollWidth?: number}) => {
  for (const [property, value] of Object.entries(widths)) {
    Object.defineProperty(element, property, {configurable: true, value});
  }
};

const make = <K extends keyof HTMLElementTagNameMap>(tag: K, className: string, parent?: HTMLElement) => {
  const element = document.createElement(tag);
  element.className = className;
  parent?.appendChild(element);
  return element;
};

interface RowLayout {
  /** The row's clientWidth, its padding included. */
  rowWidth?: number;
  /** Left and right padding of the row, each (px). */
  rowPadding?: number;
  columnGap?: string;
  /** --itg-menu-logo-slot on the header; '' when the sheet does not set it. */
  logoSlot?: string;
  menuItemWidths?: number[];
  /** The list is still the loading skeleton. */
  skeleton?: boolean;
  dateWidth?: number;
  member?: {width: number; paddingLeft: string; label?: LabelBox} | null;
  utilityMarginRight?: string;
}

/** The member label's box; `maxWidth` is its computed max-width (member.css caps it at 16rem). */
interface LabelBox {
  scrollWidth: number;
  clientWidth: number;
  maxWidth?: string;
}

/**
 * The default row needs 717px inside its padding: logo slot 48 + menu 300 + column gap 16 + date 180
 * + gap 12 + divider 12 + member 138 (150 less its 12px divider padding) + utility margin 10, + 1px slack.
 * With 20px padding on each side the date fits at a clientWidth of 757 and not at 756.
 */
const FITS_EXACTLY_PX = 757;

const makeHeader = ({
  rowWidth = FITS_EXACTLY_PX,
  rowPadding = 20,
  columnGap = '16px',
  logoSlot = '48px',
  menuItemWidths = [100, 120, 80],
  skeleton = false,
  dateWidth = 180,
  member = {width: 150, paddingLeft: '12px', label: {scrollWidth: 90, clientWidth: 90}},
  utilityMarginRight = '10px',
}: RowLayout = {}) => {
  const header = make('header', 'site-header');
  computedStyles.set(header, {vars: logoSlot ? {'--itg-menu-logo-slot': logoSlot} : {}});
  const inner = make('div', 'site-header-container site-header-menu-inner', make('div', 'site-header-menu', header));
  computedStyles.set(inner, {paddingLeft: `${rowPadding}px`, paddingRight: `${rowPadding}px`, columnGap});
  setBoxWidths(inner, {clientWidth: rowWidth});

  const list = make('ul', `menu-bar-list${skeleton ? ' menu-bar-list--skeleton' : ''}`, make('nav', 'site-header-nav', inner));
  for (const width of menuItemWidths) setWidth(make('li', 'menu-bar-item', list), width);

  const utility = make('div', 'site-header-utility', inner);
  computedStyles.set(utility, {marginRight: utilityMarginRight});
  const date = make('time', 'site-header-date', utility);
  date.textContent = 'Thursday 29 October 2026';
  setWidth(date, dateWidth);

  let label: HTMLSpanElement | null = null;
  if (member) {
    const memberElement = make('div', 'site-header-member', utility);
    computedStyles.set(memberElement, {paddingLeft: member.paddingLeft});
    setWidth(memberElement, member.width);
    if (member.label) {
      const {maxWidth, ...box} = member.label;
      label = make('span', 'member-label', memberElement);
      label.textContent = 'member@example.com';
      setBoxWidths(label, box);
      if (maxWidth !== undefined) computedStyles.set(label, {maxWidth});
    }
  }
  return {
    header,
    inner,
    list,
    date,
    label,
    ref: {current: header},
    setRowWidth: (width: number) => setBoxWidths(inner, {clientWidth: width}),
  };
};

/** Stands in for the browser's ResizeObserver, which jsdom does not implement. */
class ResizeObserverStub {
  static instances: ResizeObserverStub[] = [];
  readonly observed: Element[] = [];
  disconnected = false;
  private readonly callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
    ResizeObserverStub.instances.push(this);
  }

  observe(target: Element) {
    this.observed.push(target);
  }

  unobserve() {}

  disconnect() {
    this.disconnected = true;
  }

  /** Delivers a notification, as the browser does after layout. */
  notify() {
    this.callback([], this as unknown as ResizeObserver);
  }
}

const installResizeObserverStub = () => {
  ResizeObserverStub.instances = [];
  vi.stubGlobal('ResizeObserver', ResizeObserverStub);
};

/** Collects requested animation frames (ids 1, 2, ...) so a test can run them one at a time. */
const collectFrames = () => {
  const frames: FrameRequestCallback[] = [];
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
    frames.push(callback);
    return frames.length;
  });
  return frames;
};

/** A document.fonts stand-in (jsdom has none) whose `ready` promise the test settles. */
const installFonts = () => {
  let resolveReady = () => {};
  const ready = new Promise<void>((resolve) => {
    resolveReady = () => resolve();
  });
  const fonts = Object.assign(new EventTarget(), {ready});
  Object.defineProperty(document, 'fonts', {configurable: true, value: fonts});
  return {fonts, resolveReady};
};

/** The viewport width the hook's first guess reads. */
const setViewportWidth = (width: number) => vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(width);

/** Lets queued microtasks (MutationObserver records, settled promises) run. */
const flushMicrotasks = () => act(async () => {});

afterEach(() => {
  cleanup();
  computedStyles.clear();
  Reflect.deleteProperty(document, 'fonts');
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** The date fits in a row `rowWidth` px wide, and not in one a pixel narrower. */
const expectFitsFrom = (rowWidth: number, layout: RowLayout = {}) => {
  expect(measureDateHidden(makeHeader({...layout, rowWidth}).header)).toBe(false);
  expect(measureDateHidden(makeHeader({...layout, rowWidth: rowWidth - 1}).header)).toBe(true);
};

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
