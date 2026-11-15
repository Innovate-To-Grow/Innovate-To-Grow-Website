import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MainMenu} from '@/features/layout/components/MainMenu/menu/MainMenu';
import {makeState} from '@/__tests__/features/layout/components/MainMenu/menu/mainMenuFixtures';

const useMainMenuState = vi.hoisted(() => vi.fn());
const useHeaderDateHidden = vi.hoisted(() => vi.fn());

vi.mock('@/features/layout/components/MainMenu/menu/useMainMenuState', () => ({
  useMainMenuState,
}));

vi.mock('@/features/layout/components/MainMenu/header/useHeaderDateFit', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/layout/components/MainMenu/header/useHeaderDateFit')>()),
  useHeaderDateHidden,
}));

vi.mock('@/features/layout/components/MainMenu/parts/MemberMenu', () => ({
  MemberMenu: () => null,
}));

vi.mock('@/features/layout/components/MainMenu/parts/MobileMenuPanel', () => ({
  MobileMenuPanel: () => null,
}));

vi.mock('@/components/ResponsiveBrandImage/ResponsiveBrandImage', () => ({
  ResponsiveBrandImage: ({brand, alt, sizes}: {brand: string; alt: string; sizes?: string}) => (
    <img alt={alt} data-brand={brand} data-sizes={sizes} />
  ),
}));

const HEIGHT_PROPERTIES = ['--itg-header-bar-height', '--itg-header-menu-height'];

const setScrollY = (value: number) => {
  Object.defineProperty(window, 'scrollY', {configurable: true, value});
};

/** Gives the header parts these heights (px); every other element measures 0. */
const stubPartHeights = (heights: Record<string, number>) =>
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const part = Object.keys(heights).find((className) => this.classList.contains(className));
    const height = part ? heights[part] : 0;
    return {height, width: 0, top: 0, left: 0, right: 0, bottom: height, x: 0, y: 0, toJSON: () => ({})} as DOMRect;
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
