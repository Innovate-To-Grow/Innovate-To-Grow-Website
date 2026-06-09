import {renderHook} from '@testing-library/react';
import {type ReactNode} from 'react';
import {describe, expect, it} from 'vitest';

import {LayoutContext, useFooter, useLayout, useMenu} from '@/features/layout/components/LayoutProvider/context';
import type {LayoutContextValue} from '@/features/layout/components/LayoutProvider/context';

const wrapperFor = (value: LayoutContextValue) =>
  function Wrapper({children}: {children: ReactNode}) {
    return <LayoutContext.Provider value={value}>{children}</LayoutContext.Provider>;
  };

describe('LayoutProvider context hooks', () => {
  it('returns the default layout context outside a provider', () => {
    const {result} = renderHook(() => useLayout());

    expect(result.current).toMatchObject({
      state: 'loading',
      menus: [],
      footer: null,
      error: null,
    });
  });

  it('prioritizes main navigation menu names and falls back to the first menu', () => {
    const menus = [
      {id: '1', name: 'fallback', display_name: 'Fallback', description: null, items: [], created_at: '', updated_at: ''},
      {id: '2', name: 'main_nav', display_name: 'Main nav', description: null, items: [], created_at: '', updated_at: ''},
    ];
    const {result} = renderHook(() => useMenu(), {
      wrapper: wrapperFor({state: 'ready', menus, footer: null, error: null}),
    });

    expect(result.current.menu?.name).toBe('main_nav');

    const fallback = renderHook(() => useMenu(), {
      wrapper: wrapperFor({state: 'ready', menus: [menus[0]], footer: null, error: null}),
    });
    expect(fallback.result.current.menu?.name).toBe('fallback');
  });

  it('returns footer content together with load state and errors', () => {
    const footer = {
      id: 'footer',
      name: 'Footer',
      slug: 'footer',
      content: {},
      is_active: true,
      created_at: '',
      updated_at: '',
    };

    const {result} = renderHook(() => useFooter(), {
      wrapper: wrapperFor({state: 'error', menus: [], footer, error: 'offline'}),
    });

    expect(result.current).toEqual({footer, state: 'error', error: 'offline'});
  });
});
