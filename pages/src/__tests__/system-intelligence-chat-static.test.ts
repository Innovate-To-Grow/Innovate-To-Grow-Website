/// <reference types="node" />

import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import {afterEach, beforeEach, describe, expect, it} from 'vitest';

declare global {
  interface Window {
    SystemIntelligenceChat: {
      link: (href: string, text: string) => HTMLElement;
      renderRichText: (container: HTMLElement, text: string) => void;
    };
  }
}

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

const uuid = '11111111-2222-4333-8444-555555555555';

function installChatShell() {
  document.body.innerHTML = `
    <script id="si-chat-config" type="application/json">
      {
        "uuidPlaceholder": "00000000-0000-0000-0000-000000000000",
        "urls": {
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
    <button data-si-sidebar-toggle></button>
    <span data-si-sidebar-toggle-icon></span>
  `;
  window.eval(stateScript);
  window.eval(renderScript);
}

describe('System Intelligence static chat link rendering', () => {
  beforeEach(() => {
    installChatShell();
  });

  afterEach(() => {
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
});
