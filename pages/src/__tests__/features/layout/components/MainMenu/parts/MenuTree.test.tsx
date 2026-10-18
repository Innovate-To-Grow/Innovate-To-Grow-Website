import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {useState} from 'react';
import {afterEach, describe, expect, it} from 'vitest';

import type {MenuItem} from '@/features/layout/api';
import {MenuTree} from '@/features/layout/components/MainMenu/parts/MenuTree';

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

  it('underlines the current section and marks the current page in its dropdown', () => {
    const {container} = render(
      <MenuTree
        items={[...items, {title: 'News', url: '/news', type: 'app', open_in_new_tab: false, children: []}]}
        openItemIndex={null}
        current={{menuIndex: 0, currentPath: '/child', isExact: true}}
        onDesktopOpen={() => {}}
        onDesktopClose={() => {}}
        onDesktopToggle={() => {}}
      />,
    );

    const [parentItem, newsItem] = Array.from(container.querySelectorAll('.menu-bar-item'));
    expect(parentItem).toHaveClass('is-current');
    expect(newsItem).not.toHaveClass('is-current');
    // The section is "current" (not the page itself) when a child page is shown.
    expect(screen.getByRole('link', {name: 'Parent'})).toHaveAttribute('aria-current', 'true');
    expect(screen.getByRole('link', {name: 'Child'})).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', {name: 'News'})).not.toHaveAttribute('aria-current');
  });

  it('marks the section link as the page itself on the section landing page', () => {
    render(
      <MenuTree
        items={items}
        openItemIndex={null}
        current={{menuIndex: 0, currentPath: '/parent', isExact: true}}
        onDesktopOpen={() => {}}
        onDesktopClose={() => {}}
        onDesktopToggle={() => {}}
      />,
    );

    expect(screen.getByRole('link', {name: 'Parent'})).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', {name: 'Child'})).not.toHaveAttribute('aria-current');
  });

  it('opens external items in a new tab only when configured', () => {
    render(
      <MenuTree
        items={[
          {title: 'Out', url: 'https://example.com', type: 'external', open_in_new_tab: true, children: []},
          {title: 'Same', url: 'https://example.org', type: 'external', open_in_new_tab: false, children: []},
        ]}
        openItemIndex={null}
        onDesktopOpen={() => {}}
        onDesktopClose={() => {}}
        onDesktopToggle={() => {}}
      />,
    );

    expect(screen.getByRole('link', {name: 'Out'})).toHaveAttribute('target', '_blank');
    expect(screen.getByRole('link', {name: 'Out'})).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getByRole('link', {name: 'Same'})).not.toHaveAttribute('target');
  });
});
