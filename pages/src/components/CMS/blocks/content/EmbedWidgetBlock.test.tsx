import {act, render} from '@testing-library/react';
import {describe, expect, it} from 'vitest';
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
    // Starts with a small placeholder height until content reports back.
    expect(frame.style.height).toBe('120px');

    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {type: 'i2g-embed-resize', slug: 'schedule-embed', height: 742},
        }),
      );
    });

    expect(frame.style.height).toBe('742px');
  });

  it('ignores postMessage events for a different slug', () => {
    const {container} = render(<EmbedWidgetBlock data={{slug: 'schedule-embed'}} />);
    const frame = container.querySelector('.cms-embed-widget__frame') as HTMLElement;

    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {type: 'i2g-embed-resize', slug: 'other-widget', height: 900},
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
});
