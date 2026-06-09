import {act, render} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {EmbedBlock} from '../EmbedBlock';

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

  describe('auto-resize via postMessage (cooperating embeds)', () => {
    const SRC = 'https://archive.example.org/2025-fall-event.html';

    it('grows the frame to a height reported by the iframe from its own origin', () => {
      const {container} = render(<EmbedBlock data={{src: SRC}} />);
      const frame = container.querySelector('.cms-embed__frame') as HTMLElement;
      const iframe = container.querySelector('iframe') as HTMLIFrameElement;
      // Default placeholder until a height is reported.
      expect(frame.style.aspectRatio).toBe('16 / 9');

      act(() => {
        window.dispatchEvent(
          new MessageEvent('message', {
            data: {type: 'i2g-embed-resize', height: 920},
            source: iframe.contentWindow,
            origin: 'https://archive.example.org',
          }),
        );
      });

      expect(frame.style.height).toBe('920px');
      expect(frame.style.aspectRatio).toBe('');
    });

    it('ignores resize messages from a foreign origin', () => {
      const {container} = render(<EmbedBlock data={{src: SRC}} />);
      const frame = container.querySelector('.cms-embed__frame') as HTMLElement;
      const iframe = container.querySelector('iframe') as HTMLIFrameElement;

      act(() => {
        window.dispatchEvent(
          new MessageEvent('message', {
            data: {type: 'i2g-embed-resize', height: 920},
            source: iframe.contentWindow,
            origin: 'https://evil.example',
          }),
        );
      });

      expect(frame.style.height).toBe('');
      expect(frame.style.aspectRatio).toBe('16 / 9');
    });

    it('ignores resize messages from a foreign window', () => {
      const {container} = render(<EmbedBlock data={{src: SRC}} />);
      const frame = container.querySelector('.cms-embed__frame') as HTMLElement;

      act(() => {
        window.dispatchEvent(
          new MessageEvent('message', {
            data: {type: 'i2g-embed-resize', height: 920},
            // Not this iframe's contentWindow — must be rejected.
            source: window,
            origin: 'https://archive.example.org',
          }),
        );
      });

      expect(frame.style.aspectRatio).toBe('16 / 9');
    });

    it('ignores messages with a non-positive or non-numeric height', () => {
      const {container} = render(<EmbedBlock data={{src: SRC}} />);
      const frame = container.querySelector('.cms-embed__frame') as HTMLElement;
      const iframe = container.querySelector('iframe') as HTMLIFrameElement;

      act(() => {
        for (const height of [0, -50, NaN, 'tall']) {
          window.dispatchEvent(
            new MessageEvent('message', {
              data: {type: 'i2g-embed-resize', height},
              source: iframe.contentWindow,
              origin: 'https://archive.example.org',
            }),
          );
        }
      });

      expect(frame.style.aspectRatio).toBe('16 / 9');
    });

    it('does not attach a message listener when a fixed height is set', () => {
      const addSpy = vi.spyOn(window, 'addEventListener');
      render(<EmbedBlock data={{src: SRC, height: 600}} />);
      expect(addSpy.mock.calls.filter((c) => c[0] === 'message')).toEqual([]);
      addSpy.mockRestore();
    });

    it('does not attach a message listener when an aspect ratio is set', () => {
      const addSpy = vi.spyOn(window, 'addEventListener');
      render(<EmbedBlock data={{src: SRC, aspect_ratio: '4:3'}} />);
      expect(addSpy.mock.calls.filter((c) => c[0] === 'message')).toEqual([]);
      addSpy.mockRestore();
    });

    it('removes the message listener on unmount', () => {
      const addSpy = vi.spyOn(window, 'addEventListener');
      const removeSpy = vi.spyOn(window, 'removeEventListener');
      const {unmount} = render(<EmbedBlock data={{src: SRC}} />);

      const added = addSpy.mock.calls.find((c) => c[0] === 'message');
      expect(added).toBeDefined();

      unmount();
      const removed = removeSpy.mock.calls.find((c) => c[0] === 'message');
      expect(removed?.[1]).toBe(added?.[1]);

      addSpy.mockRestore();
      removeSpy.mockRestore();
    });
  });
});
