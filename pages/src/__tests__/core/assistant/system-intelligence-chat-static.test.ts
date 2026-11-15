/// <reference types="node" />

import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

declare global {
  interface Window {
    SystemIntelligenceChat: {
      appendMessage: (role: string, content: string) => AssistantMessage;
      handleStreamEvent: (eventText: string, assistant: AssistantMessage) => StreamEventResult | null;
      link: (href: string, text: string) => HTMLElement;
      readStream: (response: Response, assistant: AssistantMessage) => Promise<void>;
      renderAssistantError: (assistant: AssistantMessage, message: string) => void;
      renderRichText: (container: HTMLElement, text: string) => void;
      runCommand: (command: string, args?: string) => Promise<void>;
      selectConversation: (id: string) => Promise<void>;
      setAssistantStreaming: (assistant: AssistantMessage, streaming: boolean) => void;
      setStreaming: (streaming: boolean) => void;
      state: {currentId: string | null; streaming: boolean};
    };
  }
}

type AssistantMessage = {
  article: HTMLElement;
  body: HTMLElement;
  text: string;
};

type StreamEventResult = {
  done: boolean;
  error: string;
  event: string;
};

const testDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(testDir, '../../../../..');
const stateScript = readFileSync(
  resolve(repoRoot, 'src/apps/system_intelligence/static/system_intelligence/js/chat-state.js'),
  'utf8',
);
const renderScript = readFileSync(
  resolve(repoRoot, 'src/apps/system_intelligence/static/system_intelligence/js/chat-render.js'),
  'utf8',
);
const actionsScript = readFileSync(
  resolve(repoRoot, 'src/apps/system_intelligence/static/system_intelligence/js/chat-actions.js'),
  'utf8',
);
const streamScript = readFileSync(
  resolve(repoRoot, 'src/apps/system_intelligence/static/system_intelligence/js/chat-stream.js'),
  'utf8',
);

const uuid = '11111111-2222-4333-8444-555555555555';

function installChatShell() {
  document.body.innerHTML = `
    <script id="si-chat-config" type="application/json">
      {
        "uuidPlaceholder": "00000000-0000-0000-0000-000000000000",
        "streamTimeoutMs": 180000,
        "urls": {
          "command": "/admin/system-intelligence/00000000-0000-0000-0000-000000000000/command/",
          "exportDownload": "/admin/system-intelligence/exports/00000000-0000-0000-0000-000000000000/download/",
          "fullPreview": "/admin/system-intelligence/actions/00000000-0000-0000-0000-000000000000/preview/full/"
        }
      }
    </script>
    <input name="csrfmiddlewaretoken" value="csrf">
    <div data-si-root></div>
    <div data-si-conversations></div>
    <section data-si-messages></section>
    <h2 data-si-title></h2>
    <p data-si-status></p>
    <section data-si-alert></section>
    <form data-si-form></form>
    <textarea data-si-input></textarea>
    <input type="checkbox" data-si-plan-toggle>
    <button data-si-send></button>
    <button data-si-command="retry"></button>
    <button data-si-new-chat></button>
    <button data-si-rename></button>
    <button data-si-sidebar-toggle></button>
    <span data-si-sidebar-toggle-icon></span>
  `;
  window.eval(stateScript);
  window.eval(renderScript);
  window.eval(actionsScript);
  window.eval(streamScript);
}

describe('System Intelligence static chat link rendering', () => {
  beforeEach(() => {
    installChatShell();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    Reflect.deleteProperty(window, 'SystemIntelligenceChat');
    document.body.replaceChildren();
  });

  it('rebuilds export links from UUIDs instead of trusting message href text', () => {
    const container = document.createElement('div');

    window.SystemIntelligenceChat.renderRichText(
      container,
      `Download [members](/admin/system-intelligence/exports/${uuid}/download/) now.`,
    );

    const link = container.querySelector('a');
    expect(link).not.toBeNull();
    expect(link?.getAttribute('href')).toBe(`/admin/system-intelligence/exports/${uuid}/download/`);
    expect(link?.textContent).toBe('members');
  });

  it('leaves unsafe and cross-origin admin-like message links inert', () => {
    const container = document.createElement('div');
    const text =
      '[bad](javascript:alert(1)) [data](data:text/html,hi) ' +
      `[spoof](https://evil.example/admin/system-intelligence/exports/${uuid}/download/)`;

    window.SystemIntelligenceChat.renderRichText(container, text);

    expect(container.querySelector('a')).toBeNull();
    expect(container.textContent).toContain('javascript:alert(1)');
    expect(container.textContent).toContain('https://evil.example/admin/system-intelligence');
  });

  it('renders direct unsafe hrefs as non-clickable text', () => {
    const node = window.SystemIntelligenceChat.link('java\tscript:alert(1)', 'Preview');

    expect(node.tagName).toBe('SPAN');
    expect(node.textContent).toBe('Preview');
    expect((node as HTMLAnchorElement).href).toBeUndefined();
  });

  it.each([
    ['relative admin path', '/admin/example/?filter=a%26b#details', '/admin/example/?filter=a%26b#details'],
    ['same-origin admin URL', `${window.location.origin}/admin/example/?filter=1#details`, '/admin/example/?filter=1#details'],
    ['external HTTPS URL', 'https://reports.example:8443/results?q=a%26b#details', 'https://reports.example:8443/results?q=a%26b#details'],
    ['external HTTP URL', 'http://reports.example/results?q=1#details', 'http://reports.example/results?q=1#details'],
  ])('preserves safe %s links and their query/fragment', (_label, href, expected) => {
    const node = window.SystemIntelligenceChat.link(href, '<img src=x onerror=alert(1)>');

    expect(node.tagName).toBe('A');
    expect(node.getAttribute('href')).toBe(expected);
    expect(node.querySelector('img')).toBeNull();
    expect(node.textContent).toBe('<img src=x onerror=alert(1)>');
    expect(node.getAttribute('rel')).toBe('noopener');
  });

  it('encodes HTML metacharacters without changing URL delimiters or existing escapes', () => {
    const href = `/admin/report'"<>/?filter=a%26b&mode=full#details'"<>`;
    const node = window.SystemIntelligenceChat.link(href, 'Preview');

    expect(node.getAttribute('href')).toBe(
      '/admin/report%27%22%3C%3E/?filter=a%26b&mode=full#details%27%22%3C%3E',
    );
    expect(new URL((node as HTMLAnchorElement).href).searchParams.get('filter')).toBe('a&b');
    expect(new URL((node as HTMLAnchorElement).href).searchParams.get('mode')).toBe('full');
  });

  it.each([
    'javascript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'https://admin.example@evil.example/report',
    'https://user:password@reports.example/report',
    `${window.location.origin}/outside-admin/`,
    `${window.location.origin}/admin/../outside-admin/`,
    'https://evil.example/admin/example/',
    '//evil.example/admin/example/',
  ])('leaves disallowed or credential-bearing URLs inert: %s', (href) => {
    const node = window.SystemIntelligenceChat.link(href, 'Preview');

    expect(node.tagName).toBe('SPAN');
    expect(node.getAttribute('href')).toBeNull();
    expect(node.textContent).toBe('Preview');
  });
});
