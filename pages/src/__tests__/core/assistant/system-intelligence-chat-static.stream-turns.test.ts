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
});
