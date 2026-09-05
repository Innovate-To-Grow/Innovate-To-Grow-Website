import {cleanup, render} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, describe, expect, it} from 'vitest';

import {LinkListBlock} from '@/features/cms/components/blocks/content/LinkListBlock';

describe('LinkListBlock', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders internal items as react-router links', () => {
    const {container} = render(
      <MemoryRouter>
        <LinkListBlock data={{items: [{label: 'Schedule', url: '/schedule'}]}} />
      </MemoryRouter>,
    );
    const link = container.querySelector('a');
    expect(link?.getAttribute('href')).toBe('/schedule');
    expect(link?.textContent).toBe('Schedule');
  });

  it('renders external items as sanitized anchors with safe target/rel', () => {
    const {container} = render(
      <MemoryRouter>
        <LinkListBlock
          data={{
            items: [{label: 'External', url: 'https://example.com', is_external: true}],
          }}
        />
      </MemoryRouter>,
    );
    const link = container.querySelector('a');
    expect(link?.getAttribute('href')).toBe('https://example.com');
    expect(link?.getAttribute('target')).toBe('_blank');
    expect(link?.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('renders the heading with the section-title class only when provided', () => {
    const {container} = render(
      <MemoryRouter>
        <LinkListBlock data={{heading: 'Useful Links', items: []}} />
      </MemoryRouter>,
    );
    expect(container.querySelector('h2.section-title')?.textContent).toBe('Useful Links');

    const {container: noHeading} = render(
      <MemoryRouter>
        <LinkListBlock data={{items: []}} />
      </MemoryRouter>,
    );
    expect(noHeading.querySelector('h2.section-title')).toBeNull();
  });

  it('appends a description after an em dash when provided', () => {
    const {container} = render(
      <MemoryRouter>
        <LinkListBlock
          data={{
            items: [
              {label: 'Schedule', url: '/schedule', description: 'View the schedule'},
            ],
          }}
        />
      </MemoryRouter>,
    );
    expect(container.textContent).toContain('— View the schedule');
  });

  it('renders every item in its own list element', () => {
    const {container} = render(
      <MemoryRouter>
        <LinkListBlock
          data={{
            items: [
              {label: 'One', url: '/one'},
              {label: 'Two', url: '/two'},
            ],
          }}
        />
      </MemoryRouter>,
    );
    expect(container.querySelectorAll('li')).toHaveLength(2);
    expect(container.querySelector('.cms-link-list-items')).not.toBeNull();
  });
});
