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

  it('renders exception diagnostics literally without creating export links or HTML', () => {
    const assistant = window.SystemIntelligenceChat.appendMessage('assistant', '');
    const message = `Failed: [download](/admin/system-intelligence/exports/${uuid}/download/) <img src=x onerror=alert(1)>`;
    window.SystemIntelligenceChat.setAssistantStreaming(assistant, true);

    window.SystemIntelligenceChat.renderAssistantError(assistant, message);

    expect(assistant.body.textContent).toBe(message);
    expect(assistant.body.querySelector('a, img')).toBeNull();
    expect(assistant.article.getAttribute('aria-busy')).toBe('false');
  });

  it('renders server error events literally without creating response links', () => {
    const assistant = window.SystemIntelligenceChat.appendMessage('assistant', '');
    const message = `Failed: [download](/admin/system-intelligence/exports/${uuid}/download/)`;

    window.SystemIntelligenceChat.handleStreamEvent(
      `event: error\ndata: ${JSON.stringify({error: message})}`,
      assistant,
    );

    expect(assistant.body.textContent).toBe(message);
    expect(assistant.body.querySelector('a')).toBeNull();
    expect(document.querySelector('[data-si-alert]')?.textContent).toBe(message);
  });
});
