import {cleanup, render} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {ContactInfoBlock} from '@/features/cms/components/blocks/content/ContactInfoBlock';

describe('ContactInfoBlock', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the section wrapper and the fixed intro copy', () => {
    const {container} = render(<ContactInfoBlock data={{items: []}} />);
    expect(container.querySelector('.cms-contact-info')).not.toBeNull();
    expect(container.textContent).toContain(
      'For any questions, comments, or inquiries about the Innovate to Grow program',
    );
  });

  it('renders a heading only when provided', () => {
    const {container} = render(
      <ContactInfoBlock data={{heading: 'Contact Us', items: []}} />,
    );
    expect(container.querySelector('h1')?.textContent).toBe('Contact Us');

    const {container: noHeading} = render(<ContactInfoBlock data={{items: []}} />);
    expect(noHeading.querySelector('h1')).toBeNull();
  });

  it('renders an email item as a mailto link', () => {
    const {container} = render(
      <ContactInfoBlock
        data={{items: [{label: 'Email', value: 'info@example.com', type: 'email'}]}}
      />,
    );
    const link = container.querySelector('a');
    expect(link?.getAttribute('href')).toBe('mailto:info@example.com');
    expect(link?.textContent).toBe('info@example.com');
  });

  it('renders a phone item as a tel link', () => {
    const {container} = render(
      <ContactInfoBlock
        data={{items: [{label: 'Phone', value: '555-0100', type: 'phone'}]}}
      />,
    );
    const link = container.querySelector('a');
    expect(link?.getAttribute('href')).toBe('tel:555-0100');
    expect(link?.textContent).toBe('555-0100');
  });

  it('renders a url item as a sanitized external link', () => {
    const {container} = render(
      <ContactInfoBlock
        data={{items: [{label: 'Website', value: 'https://example.com', type: 'url'}]}}
      />,
    );
    const link = container.querySelector('a');
    expect(link?.getAttribute('href')).toBe('https://example.com');
    expect(link?.getAttribute('target')).toBe('_blank');
    expect(link?.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('renders a text item as plain text without a link', () => {
    const {container} = render(
      <ContactInfoBlock
        data={{items: [{label: 'Office', value: 'SE2 123', type: 'text'}]}}
      />,
    );
    expect(container.querySelector('a')).toBeNull();
    expect(container.textContent).toContain('Office');
    expect(container.textContent).toContain('SE2 123');
  });

  it('renders each label inside a <strong> element', () => {
    const {container} = render(
      <ContactInfoBlock
        data={{items: [{label: 'Email', value: 'a@b.com', type: 'email'}]}}
      />,
    );
    const strong = container.querySelector('strong');
    expect(strong?.textContent).toBe('Email:');
  });
});
