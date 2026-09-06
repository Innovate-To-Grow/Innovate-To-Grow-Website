import {cleanup, render} from '@testing-library/react';
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

  it('renders external items as sanitized anchors with safe target/rel', () => {
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
  });

  it('renders the heading only when provided', () => {
    const {container} = render(
      <MemoryRouter>
        <NavigationGridBlock data={{heading: 'Explore', items: []}} />
      </MemoryRouter>,
    );
    expect(container.querySelector('h1')?.textContent).toBe('Explore');

    const {container: noHeading} = render(
      <MemoryRouter>
        <NavigationGridBlock data={{items: []}} />
      </MemoryRouter>,
    );
    expect(noHeading.querySelector('h1')).toBeNull();
  });

  it('appends a description after a colon when provided', () => {
    const {container} = render(
      <MemoryRouter>
        <NavigationGridBlock
          data={{
            items: [{title: 'Projects', url: '/projects', description: 'Browse all'}],
          }}
        />
      </MemoryRouter>,
    );
    expect(container.textContent).toContain(': Browse all');
  });

  it('appends a description after a colon on external items too', () => {
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
    expect(container.textContent).toContain(': Learn more');
  });

  it('renders each item as a projects-hub-item', () => {
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
    expect(container.querySelectorAll('.projects-hub-item')).toHaveLength(2);
    expect(container.querySelector('.projects-hub-list')).not.toBeNull();
  });
});
