import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, describe, expect, it} from 'vitest';

import {NavigationGridBlock} from '@/features/cms/components/blocks/navigation/NavigationGridBlock';

describe('NavigationGridBlock', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders internal items as react-router links', () => {
    const {container} = render(
      <MemoryRouter>
        <NavigationGridBlock data={{items: [{title: 'Projects', url: '/projects'}]}} />
      </MemoryRouter>,
    );
    const link = container.querySelector('a.projects-hub-link');
    expect(link?.getAttribute('href')).toBe('/projects');
    expect(link?.textContent).toBe('Projects');
  });

  it('renders external items as sanitized anchors with safe target/rel and a new-tab hint', () => {
    const {container} = render(
      <MemoryRouter>
        <NavigationGridBlock
          data={{
            items: [{title: 'External', url: 'https://example.com', is_external: true}],
          }}
        />
      </MemoryRouter>,
    );
    const link = container.querySelector('a.projects-hub-link');
    expect(link?.getAttribute('href')).toBe('https://example.com');
    expect(link?.getAttribute('target')).toBe('_blank');
    expect(link?.getAttribute('rel')).toBe('noopener noreferrer');
    expect(link?.querySelector('.sr-only')?.textContent).toBe(' (opens in a new tab)');
  });

  it('renders the heading as the page title only when provided', () => {
    const {container} = render(
      <MemoryRouter>
        <NavigationGridBlock data={{heading: 'Explore', items: []}} />
      </MemoryRouter>,
    );
    const heading = container.querySelector('h1');
    expect(heading?.textContent).toBe('Explore');
    expect(heading).toHaveClass('itg-page-title', 'cms-page-title');
    expect(heading).not.toHaveClass('itg-page-title-ruled');

    const {container: noHeading} = render(
      <MemoryRouter>
        <NavigationGridBlock data={{items: []}} />
      </MemoryRouter>,
    );
    expect(noHeading.querySelector('h1')).toBeNull();
  });

  it('renders each title as an h2 link with the description in its own paragraph', () => {
    const {container} = render(
      <MemoryRouter>
        <NavigationGridBlock
          data={{
            items: [{title: 'Projects', url: '/projects', description: 'Browse all'}],
          }}
        />
      </MemoryRouter>,
    );
    const title = screen.getByRole('heading', {name: 'Projects', level: 2});
    expect(title).toHaveClass('cms-navigation-grid-title');
    expect(title.querySelector('a')?.getAttribute('href')).toBe('/projects');
    const description = container.querySelector('.cms-navigation-grid-description');
    expect(description?.tagName).toBe('P');
    expect(description?.textContent).toBe('Browse all');
  });

  it('renders the description on external items too', () => {
    const {container} = render(
      <MemoryRouter>
        <NavigationGridBlock
          data={{
            items: [
              {
                title: 'External',
                url: 'https://example.com',
                is_external: true,
                description: 'Learn more',
              },
            ],
          }}
        />
      </MemoryRouter>,
    );
    expect(container.querySelector('.cms-navigation-grid-description')?.textContent).toBe('Learn more');
  });

  it('omits the description paragraph when an item has none', () => {
    const {container} = render(
      <MemoryRouter>
        <NavigationGridBlock data={{items: [{title: 'One', url: '/one'}]}} />
      </MemoryRouter>,
    );
    expect(container.querySelector('.cms-navigation-grid-description')).toBeNull();
  });

  it('renders each item as a panel in the grid list', () => {
    const {container} = render(
      <MemoryRouter>
        <NavigationGridBlock
          data={{
            items: [
              {title: 'One', url: '/one'},
              {title: 'Two', url: '/two'},
            ],
          }}
        />
      </MemoryRouter>,
    );
    const list = container.querySelector('ul.projects-hub-list');
    expect(list).toHaveClass('cms-navigation-grid-list');
    const items = container.querySelectorAll('li.projects-hub-item');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveClass('cms-navigation-grid-item', 'itg-rule-panel');
  });

  it('renders no list when there are no items or the items are malformed', () => {
    const {container} = render(
      <MemoryRouter>
        <NavigationGridBlock data={{heading: 'Empty', items: undefined as unknown as []}} />
      </MemoryRouter>,
    );
    expect(container.querySelector('ul')).toBeNull();
    expect(container.querySelector('h1')?.textContent).toBe('Empty');
  });
});
