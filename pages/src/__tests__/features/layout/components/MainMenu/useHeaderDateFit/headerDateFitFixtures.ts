import {act} from '@testing-library/react';
import {expect, vi} from 'vitest';

import {measureDateHidden} from '@/features/layout/components/MainMenu/useHeaderDateFit';

/** What getComputedStyle reports for one element; anything unset reads as the browser's default. */
interface FakeStyle {
  paddingLeft?: string;
  paddingRight?: string;
  columnGap?: string;
  marginRight?: string;
  maxWidth?: string;
  vars?: Record<string, string>;
}

export const computedStyles = new Map<Element, FakeStyle>();

export const stubComputedStyles = () =>
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

export const setWidth = (element: HTMLElement, width: number) => {
  element.getBoundingClientRect = () =>
    ({width, height: 0, top: 0, left: 0, right: width, bottom: 0, x: 0, y: 0, toJSON: () => ({})}) as DOMRect;
};

const setBoxWidths = (element: HTMLElement, widths: {clientWidth?: number; scrollWidth?: number}) => {
  for (const [property, value] of Object.entries(widths)) {
    Object.defineProperty(element, property, {configurable: true, value});
  }
};

export const make = <K extends keyof HTMLElementTagNameMap>(tag: K, className: string, parent?: HTMLElement) => {
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
export interface LabelBox {
  scrollWidth: number;
  clientWidth: number;
  maxWidth?: string;
}

/**
 * The default row needs 717px inside its padding: logo slot 48 + menu 300 + column gap 16 + date 180
 * + gap 12 + divider 12 + member 138 (150 less its 12px divider padding) + utility margin 10, + 1px slack.
 * With 20px padding on each side the date fits at a clientWidth of 757 and not at 756.
 */
export const FITS_EXACTLY_PX = 757;

export const makeHeader = ({
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
export class ResizeObserverStub {
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

export const installResizeObserverStub = () => {
  ResizeObserverStub.instances = [];
  vi.stubGlobal('ResizeObserver', ResizeObserverStub);
};

/** Collects requested animation frames (ids 1, 2, ...) so a test can run them one at a time. */
export const collectFrames = () => {
  const frames: FrameRequestCallback[] = [];
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
    frames.push(callback);
    return frames.length;
  });
  return frames;
};

/** A document.fonts stand-in (jsdom has none) whose `ready` promise the test settles. */
export const installFonts = () => {
  let resolveReady = () => {};
  const ready = new Promise<void>((resolve) => {
    resolveReady = () => resolve();
  });
  const fonts = Object.assign(new EventTarget(), {ready});
  Object.defineProperty(document, 'fonts', {configurable: true, value: fonts});
  return {fonts, resolveReady};
};

/** The viewport width the hook's first guess reads. */
export const setViewportWidth = (width: number) => vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(width);

/** Lets queued microtasks (MutationObserver records, settled promises) run. */
export const flushMicrotasks = () => act(async () => {});

/** The date fits in a row `rowWidth` px wide, and not in one a pixel narrower. */
export const expectFitsFrom = (rowWidth: number, layout: RowLayout = {}) => {
  expect(measureDateHidden(makeHeader({...layout, rowWidth}).header)).toBe(false);
  expect(measureDateHidden(makeHeader({...layout, rowWidth: rowWidth - 1}).header)).toBe(true);
};
