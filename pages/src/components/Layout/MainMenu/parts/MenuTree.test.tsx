import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {useState} from 'react';
import {afterEach, describe, expect, it} from 'vitest';

import type {MenuItem} from '../../../../features/layout/api';
import {MenuTree} from './MenuTree';

const items: MenuItem[] = [
  {
    title: 'Parent',
    url: '/parent',
    type: 'app',
    open_in_new_tab: false,
    children: [
      {
        title: 'Child',
        url: '/child',
        type: 'app',
        open_in_new_tab: false,
        children: [],
      },
    ],
  },
];

const MenuTreeHarness = () => {
  const [openItemIndex, setOpenItemIndex] = useState<number | null>(null);

  return (
    <>
      <MenuTree
        items={items}
        openItemIndex={openItemIndex}
        onDesktopOpen={(index, hasChildren) => {
          if (hasChildren) {
            setOpenItemIndex(index);
          }
        }}
        onDesktopClose={() => setOpenItemIndex(null)}
        onDesktopToggle={(index, hasChildren) => {
          if (hasChildren) {
            setOpenItemIndex((prev) => (prev === index ? null : index));
          }
        }}
      />
      <button type="button">Outside</button>
    </>
  );
};

afterEach(() => {
  cleanup();
});

describe('MenuTree', () => {
  it('opens top-level items on keyboard and moves focus into the submenu', () => {
    render(<MenuTreeHarness />);

    const parentLink = screen.getByRole('link', {name: 'Parent'});
    fireEvent.keyDown(parentLink, {key: 'ArrowDown'});

    expect(parentLink).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('link', {name: 'Child'})).toHaveFocus();
  });

  it('closes the open menu when focus leaves the menu item', () => {
    render(<MenuTreeHarness />);

    const parentLink = screen.getByRole('link', {name: 'Parent'});
    fireEvent.focus(parentLink);
    expect(parentLink).toHaveAttribute('aria-expanded', 'true');

    fireEvent.blur(parentLink, {relatedTarget: screen.getByRole('button', {name: 'Outside'})});
    expect(parentLink).toHaveAttribute('aria-expanded', 'false');
  });
});
