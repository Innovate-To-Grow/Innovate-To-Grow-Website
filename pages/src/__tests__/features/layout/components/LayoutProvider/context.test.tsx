import {cleanup, renderHook} from '@testing-library/react';
import type {ReactNode} from 'react';
import {afterEach, describe, expect, it} from 'vitest';

import type {FooterContentResponse, Menu} from '@/features/layout/api';
import {
  defaultLayoutContext,
  LayoutContext,
  type LayoutContextValue,
  useFooter,
  useLayout,
  useMenu,
} from '@/features/layout/components/LayoutProvider/context';

afterEach(() => {
  cleanup();
});

const makeMenu = (name: string): Menu => ({
  id: `menu-${name}`,
  name,
  display_name: name,
  description: null,
  items: [],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
});

const makeFooter = (): FooterContentResponse => ({
  id: 'footer-id',
  name: 'Footer',
  slug: 'footer',
  content: {},
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
});

const withValue =
  (value: LayoutContextValue) =>
  ({children}: {children: ReactNode}) => (
    <LayoutContext.Provider value={value}>{children}</LayoutContext.Provider>
  );

describe('defaultLayoutContext', () => {
  it('starts in the loading state with no menus or footer', () => {
    expect(defaultLayoutContext).toEqual({
      state: 'loading',
      menus: [],
      footer: null,
      error: null,
    });
  });
});

describe('useLayout', () => {
  it('returns the nearest LayoutContext value', () => {
    const value: LayoutContextValue = {
      state: 'ready',
      menus: [makeMenu('main')],
      footer: makeFooter(),
      error: null,
    };
    const {result} = renderHook(() => useLayout(), {
      wrapper: withValue(value),
    });
    expect(result.current).toBe(value);
  });
});

describe('useMenu', () => {
  it('prefers the main-nav menu over every fallback', () => {
    const value: LayoutContextValue = {
      ...defaultLayoutContext,
      menus: [makeMenu('other'), makeMenu('main-nav'), makeMenu('main')],
    };
    const {result} = renderHook(() => useMenu(), {wrapper: withValue(value)});
    expect(result.current.menu?.name).toBe('main-nav');
  });

  it('falls back to main_nav when main-nav is absent', () => {
    const value: LayoutContextValue = {
      ...defaultLayoutContext,
      menus: [makeMenu('main_nav'), makeMenu('main')],
    };
    const {result} = renderHook(() => useMenu(), {wrapper: withValue(value)});
    expect(result.current.menu?.name).toBe('main_nav');
  });

  it('falls back to main when neither main-nav nor main_nav exist', () => {
    const value: LayoutContextValue = {
      ...defaultLayoutContext,
      menus: [makeMenu('main'), makeMenu('other')],
    };
    const {result} = renderHook(() => useMenu(), {wrapper: withValue(value)});
    expect(result.current.menu?.name).toBe('main');
  });

  it('falls back to the first available menu', () => {
    const value: LayoutContextValue = {
      ...defaultLayoutContext,
      menus: [makeMenu('first'), makeMenu('second')],
    };
    const {result} = renderHook(() => useMenu(), {wrapper: withValue(value)});
    expect(result.current.menu?.name).toBe('first');
  });

  it('returns null and propagates state/error when there are no menus', () => {
    const value: LayoutContextValue = {
      state: 'error',
      menus: [],
      footer: null,
      error: 'boom',
    };
    const {result} = renderHook(() => useMenu(), {wrapper: withValue(value)});
    expect(result.current.menu).toBeNull();
    expect(result.current.state).toBe('error');
    expect(result.current.error).toBe('boom');
  });
});

describe('useFooter', () => {
  it('returns the footer, state, and error from context', () => {
    const footer = makeFooter();
    const value: LayoutContextValue = {
      state: 'ready',
      menus: [],
      footer,
      error: null,
    };
    const {result} = renderHook(() => useFooter(), {wrapper: withValue(value)});
    expect(result.current).toEqual({footer, state: 'ready', error: null});
  });
});
