import {render} from '@testing-library/react';
import {describe, expect, it} from 'vitest';
import {EmbedBlock} from './EmbedBlock';

describe('EmbedBlock', () => {
  it('renders an iframe with https src, default sandbox, and 16/9 aspect', () => {
    const {container} = render(
      <EmbedBlock data={{src: 'https://docs.google.com/forms/d/xyz/viewform'}} />,
    );
    const iframe = container.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute('src')).toBe('https://docs.google.com/forms/d/xyz/viewform');
    expect(iframe?.getAttribute('sandbox')).toBe(
      'allow-scripts allow-same-origin allow-forms allow-popups',
    );
    expect(iframe?.getAttribute('loading')).toBe('lazy');

    const frame = container.querySelector('.cms-embed__frame') as HTMLElement | null;
    expect(frame?.style.aspectRatio).toBe('16 / 9');
  });

  it('renders a placeholder when src is non-https', () => {
    const {container} = render(<EmbedBlock data={{src: 'http://example.com/thing'}} />);
    expect(container.querySelector('iframe')).toBeNull();
    expect(container.querySelector('.cms-embed--invalid')).not.toBeNull();
  });

  it('renders a placeholder when src is missing', () => {
    const {container} = render(<EmbedBlock data={{src: ''}} />);
    expect(container.querySelector('iframe')).toBeNull();
    expect(container.querySelector('.cms-embed--invalid')).not.toBeNull();
  });

  it('applies a custom aspect ratio when provided', () => {
    const {container} = render(
      <EmbedBlock
        data={{src: 'https://docs.google.com/a', aspect_ratio: '4:3'}}
      />,
    );
    const frame = container.querySelector('.cms-embed__frame') as HTMLElement | null;
    expect(frame?.style.aspectRatio).toBe('4 / 3');
  });

  it('uses fixed height instead of aspect ratio when height is provided', () => {
    const {container} = render(
      <EmbedBlock data={{src: 'https://docs.google.com/a', height: 600}} />,
    );
    const frame = container.querySelector('.cms-embed__frame') as HTMLElement | null;
    expect(frame?.style.height).toBe('600px');
    expect(frame?.style.aspectRatio).toBe('');
  });

  it('allows overriding the sandbox and sets allowfullscreen', () => {
    const {container} = render(
      <EmbedBlock
        data={{
          src: 'https://docs.google.com/a',
          sandbox: 'allow-scripts',
          allowfullscreen: true,
        }}
      />,
    );
    const iframe = container.querySelector('iframe');
    expect(iframe?.getAttribute('sandbox')).toBe('allow-scripts');
    expect(iframe?.getAttribute('allowfullscreen')).not.toBeNull();
  });

  it('renders a heading when provided', () => {
    const {getByRole} = render(
      <EmbedBlock data={{src: 'https://docs.google.com/a', heading: 'My Form'}} />,
    );
    expect(getByRole('heading', {name: 'My Form'})).not.toBeNull();
  });

  it('uses explicit title on the iframe when provided', () => {
    const {container} = render(
      <EmbedBlock
        data={{src: 'https://docs.google.com/a', title: 'RSVP Form', heading: 'Sign up'}}
      />,
    );
    expect(container.querySelector('iframe')?.getAttribute('title')).toBe('RSVP Form');
  });

  it('falls back to heading as iframe title when title is missing', () => {
    const {container} = render(
      <EmbedBlock data={{src: 'https://docs.google.com/a', heading: 'Sign up'}} />,
    );
    expect(container.querySelector('iframe')?.getAttribute('title')).toBe('Sign up');
  });

  it('falls back to "Embedded content" when neither title nor heading is set', () => {
    const {container} = render(<EmbedBlock data={{src: 'https://docs.google.com/a'}} />);
    expect(container.querySelector('iframe')?.getAttribute('title')).toBe('Embedded content');
  });

  it('falls back to the default sandbox when an empty string is supplied', () => {
    const {container} = render(
      <EmbedBlock data={{src: 'https://docs.google.com/a', sandbox: ''}} />,
    );
    expect(container.querySelector('iframe')?.getAttribute('sandbox')).toBe(
      'allow-scripts allow-same-origin allow-forms allow-popups',
    );
  });

  it('renders the heading with the .section-title class so host CSS targets it', () => {
    const {container} = render(
      <EmbedBlock data={{src: 'https://docs.google.com/a', heading: 'My Form'}} />,
    );
    const heading = container.querySelector('h2.section-title');
    expect(heading).not.toBeNull();
    expect(heading?.textContent).toBe('My Form');
  });
});
