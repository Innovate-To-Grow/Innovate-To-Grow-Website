import {act, render} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {EmbedWidgetBlock} from './EmbedWidgetBlock';

describe('EmbedWidgetBlock', () => {
  it('renders an iframe pointing at /_embed/<slug> with a safe sandbox', () => {
    const {container} = render(<EmbedWidgetBlock data={{slug: 'schedule-embed'}} />);
    const iframe = container.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute('src')).toBe('/_embed/schedule-embed');
    expect(iframe?.getAttribute('sandbox')).toBe(
      'allow-scripts allow-same-origin allow-popups allow-forms',
    );
    expect(iframe?.getAttribute('loading')).toBe('lazy');
  });

  it('appends ?hide-titles=1 when hide_section_titles is set', () => {
    const {container} = render(
      <EmbedWidgetBlock data={{slug: 'schedule-embed', hide_section_titles: true}} />,
    );
    const iframe = container.querySelector('iframe');
    expect(iframe?.getAttribute('src')).toBe('/_embed/schedule-embed?hide-titles=1');
  });

  it('appends ?hide-sections=<keys> when hidden_sections is set', () => {
    const {container} = render(
      <EmbedWidgetBlock data={{slug: 'schedule-embed', hidden_sections: ['schedule_header', 'schedule_projects']}} />,
    );
    const iframe = container.querySelector('iframe');
    expect(iframe?.getAttribute('src')).toBe(
      '/_embed/schedule-embed?hide-sections=schedule_header%2Cschedule_projects',
    );
  });

  it('treats hidden_sections as authoritative over legacy hide_section_titles', () => {
    const {container} = render(
      <EmbedWidgetBlock data={{slug: 'schedule-embed', hidden_sections: [], hide_section_titles: true}} />,
    );
    const iframe = container.querySelector('iframe');
    expect(iframe?.getAttribute('src')).toBe('/_embed/schedule-embed');
  });

  it('renders a placeholder when slug is missing or invalid', () => {
    const {container: empty} = render(<EmbedWidgetBlock data={{slug: ''}} />);
    expect(empty.querySelector('iframe')).toBeNull();
    expect(empty.querySelector('.cms-embed-widget--invalid')).not.toBeNull();

    const {container: bad} = render(<EmbedWidgetBlock data={{slug: 'Not Valid!'}} />);
    expect(bad.querySelector('iframe')).toBeNull();
    expect(bad.querySelector('.cms-embed-widget--invalid')).not.toBeNull();
  });

  it('uses fixed height when provided', () => {
    const {container} = render(
      <EmbedWidgetBlock data={{slug: 'schedule-embed', height: 480}} />,
    );
    const frame = container.querySelector('.cms-embed-widget__frame') as HTMLElement | null;
    expect(frame?.style.height).toBe('480px');
    expect(frame?.style.aspectRatio).toBe('');
  });

  it('loads eagerly and starts taller in preview mode', () => {
    const {container} = render(
      <EmbedWidgetBlock data={{slug: 'schedule-embed'}} previewMode />,
    );
    const iframe = container.querySelector('iframe');
    const frame = container.querySelector('.cms-embed-widget__frame') as HTMLElement | null;
    expect(iframe?.getAttribute('loading')).toBe('eager');
    expect(frame?.style.height).toBe('360px');
  });

  it('uses aspect ratio when provided and no fixed height', () => {
    const {container} = render(
      <EmbedWidgetBlock data={{slug: 'schedule-embed', aspect_ratio: '16:9'}} />,
    );
    const frame = container.querySelector('.cms-embed-widget__frame') as HTMLElement | null;
    expect(frame?.style.aspectRatio).toBe('16 / 9');
  });

  it('auto-resizes when receiving a matching postMessage event', () => {
    const {container} = render(<EmbedWidgetBlock data={{slug: 'schedule-embed'}} />);
    const frame = container.querySelector('.cms-embed-widget__frame') as HTMLElement;
    const iframe = container.querySelector('iframe') as HTMLIFrameElement;
    // Starts with a small placeholder height until content reports back.
    expect(frame.style.height).toBe('120px');

    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {type: 'i2g-embed-resize', slug: 'schedule-embed', height: 742},
          source: iframe.contentWindow,
          origin: window.location.origin,
        }),
      );
    });

    expect(frame.style.height).toBe('742px');
  });

  it('ignores postMessage events for a different slug', () => {
    const {container} = render(<EmbedWidgetBlock data={{slug: 'schedule-embed'}} />);
    const frame = container.querySelector('.cms-embed-widget__frame') as HTMLElement;
    const iframe = container.querySelector('iframe') as HTMLIFrameElement;

    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {type: 'i2g-embed-resize', slug: 'other-widget', height: 900},
          source: iframe.contentWindow,
          origin: window.location.origin,
        }),
      );
    });

    expect(frame.style.height).toBe('120px');
  });

  it('ignores postMessage events from a foreign window', () => {
    const {container} = render(<EmbedWidgetBlock data={{slug: 'schedule-embed'}} />);
    const frame = container.querySelector('.cms-embed-widget__frame') as HTMLElement;

    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {type: 'i2g-embed-resize', slug: 'schedule-embed', height: 900},
          // source is not this block's iframe.contentWindow — must be rejected.
          source: window,
          origin: window.location.origin,
        }),
      );
    });

    expect(frame.style.height).toBe('120px');
  });

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
