import {act, render} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {EmbedWidgetBlock} from '@/features/cms/components/blocks/content/EmbedWidgetBlock';

describe('EmbedWidgetBlock', () => {
  it('ignores postMessage events from a foreign origin', () => {
    const {container} = render(<EmbedWidgetBlock data={{slug: 'schedule-embed'}} />);
    const frame = container.querySelector('.cms-embed-widget__frame') as HTMLElement;
    const iframe = container.querySelector('iframe') as HTMLIFrameElement;

    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {type: 'i2g-embed-resize', slug: 'schedule-embed', height: 900},
          source: iframe.contentWindow,
          origin: 'https://evil.example',
        }),
      );
    });

    expect(frame.style.height).toBe('120px');
  });

  it('renders a heading when provided', () => {
    const {getByRole} = render(
      <EmbedWidgetBlock data={{slug: 'schedule-embed', heading: 'Event Schedule'}} />,
    );
    expect(getByRole('heading', {name: 'Event Schedule'})).not.toBeNull();
  });

  it('removes the message listener on unmount', () => {
    const addSpy = vi.spyOn(window, 'addEventListener');
    const removeSpy = vi.spyOn(window, 'removeEventListener');

    const {unmount} = render(<EmbedWidgetBlock data={{slug: 'schedule-embed'}} />);

    const added = addSpy.mock.calls.find((call) => call[0] === 'message');
    expect(added).toBeDefined();

    unmount();
    const removed = removeSpy.mock.calls.find((call) => call[0] === 'message');
    expect(removed).toBeDefined();
    // Same handler reference must have been removed — otherwise we leak.
    expect(removed?.[1]).toBe(added?.[1]);

    addSpy.mockRestore();
    removeSpy.mockRestore();
  });

  it('does not attach a message listener when a fixed height is set', () => {
    const addSpy = vi.spyOn(window, 'addEventListener');
    render(<EmbedWidgetBlock data={{slug: 'schedule-embed', height: 400}} />);
    const messageListeners = addSpy.mock.calls.filter((call) => call[0] === 'message');
    expect(messageListeners).toEqual([]);
    addSpy.mockRestore();
  });

  it('does not attach a message listener when an aspect ratio is set', () => {
    const addSpy = vi.spyOn(window, 'addEventListener');
    render(<EmbedWidgetBlock data={{slug: 'schedule-embed', aspect_ratio: '16:9'}} />);
    const messageListeners = addSpy.mock.calls.filter((call) => call[0] === 'message');
    expect(messageListeners).toEqual([]);
    addSpy.mockRestore();
  });

  it('ignores postMessage events with a wrong type', () => {
    const {container} = render(<EmbedWidgetBlock data={{slug: 'schedule-embed'}} />);
    const frame = container.querySelector('.cms-embed-widget__frame') as HTMLElement;
    const iframe = container.querySelector('iframe') as HTMLIFrameElement;
    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {type: 'other-message', slug: 'schedule-embed', height: 700},
          source: iframe.contentWindow,
          origin: window.location.origin,
        }),
      );
    });
    expect(frame.style.height).toBe('120px');
  });

  it('ignores postMessage events with a non-object payload', () => {
    const {container} = render(<EmbedWidgetBlock data={{slug: 'schedule-embed'}} />);
    const frame = container.querySelector('.cms-embed-widget__frame') as HTMLElement;
    const iframe = container.querySelector('iframe') as HTMLIFrameElement;
    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: 'just a string',
          source: iframe.contentWindow,
          origin: window.location.origin,
        }),
      );
      window.dispatchEvent(
        new MessageEvent('message', {
          data: null,
          source: iframe.contentWindow,
          origin: window.location.origin,
        }),
      );
      window.dispatchEvent(
        new MessageEvent('message', {
          data: 42,
          source: iframe.contentWindow,
          origin: window.location.origin,
        }),
      );
    });
    expect(frame.style.height).toBe('120px');
  });

  it('ignores postMessage events with a non-numeric height', () => {
    const {container} = render(<EmbedWidgetBlock data={{slug: 'schedule-embed'}} />);
    const frame = container.querySelector('.cms-embed-widget__frame') as HTMLElement;
    const iframe = container.querySelector('iframe') as HTMLIFrameElement;
    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {type: 'i2g-embed-resize', slug: 'schedule-embed', height: 'tall'},
          source: iframe.contentWindow,
          origin: window.location.origin,
        }),
      );
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {type: 'i2g-embed-resize', slug: 'schedule-embed', height: -300},
          source: iframe.contentWindow,
          origin: window.location.origin,
        }),
      );
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {type: 'i2g-embed-resize', slug: 'schedule-embed', height: NaN},
          source: iframe.contentWindow,
          origin: window.location.origin,
        }),
      );
    });
    expect(frame.style.height).toBe('120px');
  });

  it('lowercases and trims the slug before building the URL', () => {
    const {container} = render(
      <EmbedWidgetBlock data={{slug: '  Schedule-Embed  '}} />,
    );
    const iframe = container.querySelector('iframe');
    expect(iframe?.getAttribute('src')).toBe('/_embed/schedule-embed');
  });

  it('uses fixed height over aspect ratio when both are provided', () => {
    const {container} = render(
      <EmbedWidgetBlock
        data={{slug: 'schedule-embed', height: 720, aspect_ratio: '16:9'}}
      />,
    );
    const frame = container.querySelector('.cms-embed-widget__frame') as HTMLElement | null;
    expect(frame?.style.height).toBe('720px');
    // aspectRatio must NOT be applied — height wins.
    expect(frame?.style.aspectRatio).toBe('');
  });
});
