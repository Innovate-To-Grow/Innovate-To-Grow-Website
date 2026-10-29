import {act, cleanup, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MainMenu} from '@/features/layout/components/MainMenu/MainMenu';
import {makeState} from '@/__tests__/features/layout/components/MainMenu/mainMenuFixtures';

const useMainMenuState = vi.hoisted(() => vi.fn());
const useHeaderDateHidden = vi.hoisted(() => vi.fn());

vi.mock('@/features/layout/components/MainMenu/useMainMenuState', () => ({
  useMainMenuState,
}));

vi.mock('@/features/layout/components/MainMenu/useHeaderDateFit', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/layout/components/MainMenu/useHeaderDateFit')>()),
  useHeaderDateHidden,
}));

vi.mock('@/features/layout/components/MainMenu/parts/MemberMenu', () => ({
  MemberMenu: () => null,
}));

vi.mock('@/features/layout/components/MainMenu/parts/MobileMenuPanel', () => ({
  MobileMenuPanel: () => null,
}));

vi.mock('@/components/ResponsiveBrandImage', () => ({
  ResponsiveBrandImage: ({brand, alt, sizes}: {brand: string; alt: string; sizes?: string}) => (
    <img alt={alt} data-brand={brand} data-sizes={sizes} />
  ),
}));

const HEIGHT_PROPERTIES = ['--itg-header-bar-height', '--itg-header-menu-height'];

const setScrollY = (value: number) => {
  Object.defineProperty(window, 'scrollY', {configurable: true, value});
};

const scrollTo = (value: number) =>
  act(() => {
    setScrollY(value);
    window.dispatchEvent(new Event('scroll'));
  });

/** Gives the header parts these heights (px); every other element measures 0. */
const stubPartHeights = (heights: Record<string, number>) =>
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const part = Object.keys(heights).find((className) => this.classList.contains(className));
    const height = part ? heights[part] : 0;
    return {height, width: 0, top: 0, left: 0, right: 0, bottom: height, x: 0, y: 0, toJSON: () => ({})} as DOMRect;
  });

/** The desktop header: the 85px bar above the menu row, so the row pins at 85px. */
const stubDesktopHeader = () => stubPartHeights({'site-header-bar': 85, 'site-header-menu': 40});

/** Runs each requested animation frame straight away. */
const runFramesImmediately = () =>
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
    callback(0);
    return 1;
  });

/** Collects requested animation frames so a test can run them one at a time. */
const collectFrames = () => {
  const frames: FrameRequestCallback[] = [];
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
    frames.push(callback);
    return frames.length;
  });
  return frames;
};

const renderMenu = (overrides: Record<string, unknown> = {}) => {
  useMainMenuState.mockReturnValue(makeState(overrides));
  const navigate = vi.fn();
  const view = render(<MainMenu navigate={navigate} />);
  return {...view, header: screen.getByRole('banner'), rerenderMenu: () => view.rerender(<MainMenu navigate={navigate} />)};
};

describe('MainMenu header state', () => {
  beforeEach(() => {
    useMainMenuState.mockReset();
    useHeaderDateHidden.mockReset();
    useHeaderDateHidden.mockReturnValue(false);
  });

  afterEach(() => {
    cleanup();
    setScrollY(0);
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    for (const property of HEIGHT_PROPERTIES) document.documentElement.style.removeProperty(property);
  });

  describe('condensed menu row', () => {
    it('condenses the banner once the menu row pins at 85px, and lets go only below 77px', () => {
      runFramesImmediately();
      stubDesktopHeader();
      const {header} = renderMenu();
      expect(header).not.toHaveClass('is-condensed');

      scrollTo(84);
      expect(header).not.toHaveClass('is-condensed');
      scrollTo(85);
      expect(header).toHaveClass('is-condensed');

      // 8px of hysteresis: scroll jitter at the threshold cannot flicker.
      scrollTo(77);
      expect(header).toHaveClass('is-condensed');
      scrollTo(76);
      expect(header).not.toHaveClass('is-condensed');

      // Coming back down, it waits for the row to pin again.
      scrollTo(80);
      expect(header).not.toHaveClass('is-condensed');
      scrollTo(260);
      expect(header).toHaveClass('is-condensed');
      scrollTo(0);
      expect(header).not.toHaveClass('is-condensed');
    });

    it('starts condensed, without motion, when the page loads already scrolled past the bar', () => {
      collectFrames();
      stubDesktopHeader();
      setScrollY(300);
      const {header} = renderMenu();

      expect(header).toHaveClass('is-condensed');
      expect(header).not.toHaveClass('has-motion');
    });

    it('switches motion on only after two animation frames', () => {
      const frames = collectFrames();
      stubDesktopHeader();
      const {header} = renderMenu();
      expect(header).not.toHaveClass('has-motion');
      expect(frames).toHaveLength(1);

      act(() => frames[0](0));
      expect(header).not.toHaveClass('has-motion');
      expect(frames).toHaveLength(2);

      act(() => frames[1](0));
      expect(header).toHaveClass('has-motion');
      expect(header).not.toHaveClass('is-condensed');
    });

    it('never condenses the phone header', () => {
      runFramesImmediately();
      stubDesktopHeader();
      vi.stubGlobal(
        'matchMedia',
        (query: string) => ({matches: query === '(max-width: 992px)', media: query}) as MediaQueryList,
      );
      setScrollY(600);
      const {header} = renderMenu();
      expect(header).not.toHaveClass('is-condensed');

      scrollTo(900);
      expect(header).not.toHaveClass('is-condensed');
    });

    it('puts the round logo link at the front of the menu row, beside the bar logo', () => {
      const {container, header} = renderMenu();
      const inner = container.querySelector('.site-header-menu-inner') as HTMLElement;
      const logo = inner.firstElementChild as HTMLElement;

      expect(logo).toBe(within(inner).getByRole('link', {name: 'Innovate To Grow home'}));
      expect(logo.tagName).toBe('A');
      expect(logo).toHaveClass('site-header-menu-logo');
      expect(logo).toHaveAttribute('href', '/');
      expect(logo).toHaveAttribute('aria-label', 'Innovate To Grow home');
      // A decorative round logo: the link's label names it.
      const image = logo.querySelector('img') as HTMLImageElement;
      expect(image).toHaveAttribute('data-brand', 'i2g');
      expect(image).toHaveAttribute('alt', '');
      expect(image).toHaveAttribute('data-sizes', '32px');
      expect(logo.nextElementSibling).toBe(screen.getByRole('navigation', {name: 'Main menu'}));

      // It is in the row at every scroll position (the stylesheet shows it while condensed),
      // and the blue bar keeps its own home link.
      expect(header).not.toHaveClass('is-condensed');
      const bar = container.querySelector('.site-header-bar') as HTMLElement;
      expect(within(bar).getByRole('link', {name: 'Innovate To Grow home'})).not.toBe(logo);
    });
  });

  describe('date fit', () => {
    it('hides the date while useHeaderDateHidden says it does not fit, measuring the header', () => {
      useHeaderDateHidden.mockReturnValue(true);
      const {container, header, rerenderMenu} = renderMenu();

      expect(header).toHaveClass('is-date-hidden');
      expect(useHeaderDateHidden).toHaveBeenCalledWith(expect.objectContaining({current: header}));
      // The date stays in the row (unseen) so it can be measured again.
      expect(container.querySelector('.site-header-utility time.site-header-date')).not.toBeNull();

      useHeaderDateHidden.mockReturnValue(false);
      rerenderMenu();
      expect(header).not.toHaveClass('is-date-hidden');
    });
  });

  describe('header classes', () => {
    it('carries only the flags that are on', () => {
      collectFrames();
      const {header} = renderMenu();
      expect(header.className).toBe('site-header');
      cleanup();

      useHeaderDateHidden.mockReturnValue(true);
      const {header: openHeader} = renderMenu({isMobileOpen: true});
      expect(openHeader.className).toBe('site-header is-date-hidden is-mobile-open');
    });

    it('marks the header while the mobile menu is open', () => {
      const {header} = renderMenu({isMobileOpen: true});
      expect(header).toHaveClass('is-mobile-open');
    });

    it('publishes the header part heights as CSS custom properties', () => {
      stubPartHeights({'site-header-bar': 85, 'site-header-menu': 44});
      renderMenu();

      const style = document.documentElement.style;
      expect(style.getPropertyValue('--itg-header-bar-height')).toBe('85px');
      expect(style.getPropertyValue('--itg-header-menu-height')).toBe('44px');
    });
  });
});
