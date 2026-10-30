import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

vi.mock('@/features/assistant/api', () => ({
  DEFAULT_ASSISTANT_CONFIG: {
    enabled: true,
    welcome_message: 'Welcome!',
    starter_questions: [],
    unavailable_message: 'Offline.',
    max_message_chars: 2000,
  },
  fetchAssistantConfig: () => new Promise(() => {}),
  sendAssistantMessage: vi.fn(),
}));

import {AssistantWidget} from '@/features/assistant/components/AssistantWidget';
import {coversPageControl} from '@/features/assistant/components/useLauncherYield';

const LAUNCHER_BOX = new DOMRect(318, 772, 56, 56);

function pageWith(markup: string) {
  const page = document.createElement('div');
  page.innerHTML = markup;
  document.body.appendChild(page);
  return page;
}

describe('coversPageControl', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it("finds the pager's Next button under the launcher", () => {
    const page = pageWith('<nav><button type="button">Next</button></nav>');
    const widget = pageWith('<button type="button">Open chat assistant</button>');
    const next = page.querySelector('button')!;
    const hitTest = vi.fn((x: number) => (x > 340 ? [widget.firstElementChild!, next, page, document.body] : [document.body]));

    expect(coversPageControl(LAUNCHER_BOX, widget, hitTest)).toBe(true);
  });

  it("finds a link through the text inside it, and ignores the widget's own button", () => {
    const page = pageWith('<a href="/projects/abc"><span>Solar drone</span></a>');
    const widget = pageWith('<button type="button">Open chat assistant</button>');

    expect(coversPageControl(LAUNCHER_BOX, widget, () => [page.querySelector('span')!])).toBe(true);
    expect(coversPageControl(LAUNCHER_BOX, widget, () => [widget.firstElementChild!, document.body])).toBe(false);
  });

  it('lets the launcher sit over plain text', () => {
    const page = pageWith('<p>Team members: Kyle On</p>');
    const widget = pageWith('<button type="button">Open chat assistant</button>');

    expect(coversPageControl(LAUNCHER_BOX, widget, () => [page.querySelector('p')!, document.body])).toBe(false);
  });

  it('samples the whole box, corners included', () => {
    const widget = pageWith('<span></span>');
    const points: Array<[number, number]> = [];

    coversPageControl(LAUNCHER_BOX, widget, (x, y) => {
      points.push([x, y]);
      return [];
    });

    expect(points).toHaveLength(9);
    expect(points).toContainEqual([320, 774]);
    expect(points).toContainEqual([372, 826]);
  });
});

describe('AssistantWidget launcher', () => {
  let underLauncher: Element[];

  beforeEach(() => {
    underLauncher = [];
    document.elementsFromPoint = vi.fn(() => underLauncher);
  });

  afterEach(() => {
    cleanup();
    document.body.innerHTML = '';
    delete (document as {elementsFromPoint?: unknown}).elementsFromPoint;
  });

  it('tucks into the page gutter while a page control is under its spot, and comes back after', async () => {
    const next = pageWith('<button type="button">Next</button>').firstElementChild!;
    render(<AssistantWidget />);
    const launcher = screen.getByRole('button', {name: 'Open chat assistant'});
    expect(launcher).not.toHaveClass('is-tucked');

    underLauncher = [next];
    act(() => {
      window.dispatchEvent(new Event('scroll'));
    });
    await waitFor(() => expect(launcher).toHaveClass('is-tucked'));

    underLauncher = [document.body];
    act(() => {
      window.dispatchEvent(new Event('scroll'));
    });
    await waitFor(() => expect(launcher).not.toHaveClass('is-tucked'));
  });

  it('stays whole while the chat is open', async () => {
    underLauncher = [pageWith('<button type="button">Next</button>').firstElementChild!];
    render(<AssistantWidget />);
    const launcher = screen.getByRole('button', {name: 'Open chat assistant'});
    await waitFor(() => expect(launcher).toHaveClass('is-tucked'));

    fireEvent.click(launcher);

    expect(launcher).toHaveAttribute('aria-expanded', 'true');
    expect(launcher).not.toHaveClass('is-tucked');
  });
});
