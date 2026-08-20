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
const repoRoot = resolve(testDir, '../../..');
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

  it('parses CRLF SSE frames and fields without a required space', () => {
    const assistant = window.SystemIntelligenceChat.appendMessage('assistant', '');
    window.SystemIntelligenceChat.setAssistantStreaming(assistant, true);

    const result = window.SystemIntelligenceChat.handleStreamEvent(
      'event:text\r\ndata:{"chunk":"Hello"}',
      assistant,
    );

    expect(result).toEqual({event: 'text', error: '', done: false});
    expect(assistant.text).toBe('Hello');
    expect(assistant.body.textContent).toBe('Hello');
    expect(assistant.article.getAttribute('aria-busy')).toBe('true');
  });

  it('ignores SSE heartbeat comments without treating them as messages', () => {
    const assistant = window.SystemIntelligenceChat.appendMessage('assistant', '');

    const result = window.SystemIntelligenceChat.handleStreamEvent(': keep-alive', assistant);

    expect(result).toBeNull();
    expect(assistant.text).toBe('');
  });

  it('surfaces streamed errors and clears the pending assistant state', () => {
    const assistant = window.SystemIntelligenceChat.appendMessage('assistant', '');
    assistant.article.classList.add('is-streaming');

    const result = window.SystemIntelligenceChat.handleStreamEvent(
      'event: error\ndata: {"error":"Bedrock denied the request."}',
      assistant,
    );

    expect(result).toEqual({event: 'error', error: 'Bedrock denied the request.', done: false});
    expect(assistant.article.classList.contains('is-streaming')).toBe(false);
    expect(assistant.body.textContent).toBe('Bedrock denied the request.');
    expect(document.querySelector('[data-si-alert]')?.textContent).toBe('Bedrock denied the request.');
  });

  it('reads incrementally chunked CRLF frames through a terminal done event', async () => {
    const assistant = window.SystemIntelligenceChat.appendMessage('assistant', '');
    const encoder = new TextEncoder();
    const chunks = [
      encoder.encode('event:text\r\ndata:{"chunk":"Hel'),
      encoder.encode('lo"}\r\n\r\nevent:done\r\ndata:{}\r\n\r\n'),
    ];
    let index = 0;
    const response = {
      body: {
        getReader: () => ({
          read: async () =>
            index < chunks.length ? {value: chunks[index++], done: false} : {value: undefined, done: true},
        }),
      },
      headers: {get: () => 'text/event-stream'},
      ok: true,
      redirected: false,
      url: '',
    } as unknown as Response;

    await window.SystemIntelligenceChat.readStream(response, assistant);

    expect(assistant.text).toBe('Hello');
    expect(assistant.body.textContent).toBe('Hello');
  });

  it('rejects a stream that closes without done', async () => {
    const assistant = window.SystemIntelligenceChat.appendMessage('assistant', '');
    const encoder = new TextEncoder();
    let delivered = false;
    const response = {
      body: {
        getReader: () => ({
          read: async () => {
            if (delivered) return {value: undefined, done: true};
            delivered = true;
            return {value: encoder.encode('event: text\ndata: {"chunk":"partial"}\n\n'), done: false};
          },
        }),
      },
      headers: {get: () => 'text/event-stream'},
      ok: true,
      redirected: false,
      url: '',
    } as unknown as Response;

    await expect(window.SystemIntelligenceChat.readStream(response, assistant)).rejects.toThrow(
      'ended before it was complete',
    );
  });

  it('locks all turn controls and rejects overlapping commands while streaming', async () => {
    window.SystemIntelligenceChat.setStreaming(true);

    expect((document.querySelector('[data-si-send]') as HTMLButtonElement).disabled).toBe(true);
    expect((document.querySelector('[data-si-input]') as HTMLTextAreaElement).disabled).toBe(true);
    expect((document.querySelector('[data-si-plan-toggle]') as HTMLInputElement).disabled).toBe(true);
    expect((document.querySelector('[data-si-command]') as HTMLButtonElement).disabled).toBe(true);
    expect((document.querySelector('[data-si-new-chat]') as HTMLButtonElement).disabled).toBe(true);
    expect((document.querySelector('[data-si-rename]') as HTMLButtonElement).disabled).toBe(true);
    await expect(window.SystemIntelligenceChat.runCommand('retry')).rejects.toThrow(
      'Wait for the current assistant response',
    );

    window.SystemIntelligenceChat.setStreaming(false);
    expect((document.querySelector('[data-si-command]') as HTMLButtonElement).disabled).toBe(false);
  });

  it('keeps a completed streamed answer when the conversation refresh fails', async () => {
    const encoder = new TextEncoder();
    const chunks = [encoder.encode('event:text\ndata:{"chunk":"Completed answer"}\n\nevent:done\ndata:{}\n\n')];
    let index = 0;
    const response = {
      body: {
        getReader: () => ({
          read: async () =>
            index < chunks.length ? {value: chunks[index++], done: false} : {value: undefined, done: true},
        }),
      },
      headers: {get: () => 'text/event-stream'},
      ok: true,
    } as unknown as Response;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    window.SystemIntelligenceChat.state.currentId = uuid;
    window.SystemIntelligenceChat.selectConversation = vi.fn().mockRejectedValue(new Error('refresh failed'));

    await expect(window.SystemIntelligenceChat.runCommand('retry')).rejects.toThrow(
      'The response completed, but the conversation could not refresh. refresh failed',
    );

    const assistant = document.querySelector('.si-message-assistant .si-message-body');
    expect(assistant?.textContent).toBe('Completed answer');
  });
});
