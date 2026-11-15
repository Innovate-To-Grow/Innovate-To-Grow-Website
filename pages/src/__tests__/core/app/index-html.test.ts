/// <reference types="node" />

import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import postcss from 'postcss';
import {afterEach, describe, expect, it} from 'vitest';

/** A file under pages/src, read from this test's place in it. */
const readSource = (path: string) => readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../..', path), 'utf8');

const indexHtml = readSource('../index.html');
const shell = new DOMParser().parseFromString(indexHtml, 'text/html');
const inline = Array.from(shell.head.querySelectorAll('style'), (node) => node.textContent).join('\n');
/** Mounts index.html's body and inline critical CSS into the test document. */
const mountShell = ({isolated}: {isolated: boolean}) => {
  const style = document.createElement('style');
  style.textContent = inline;
  document.head.appendChild(style);
  document.body.innerHTML = shell.body.innerHTML;
  if (isolated) document.documentElement.dataset.blockPreview = '';
};

afterEach(() => {
  document.head.querySelectorAll('style').forEach((node) => node.remove());
  document.body.innerHTML = '';
  delete document.documentElement.dataset.blockPreview;
});

describe('index.html page shell', () => {
  it('wraps the app root in one native <main id="main"> landmark', () => {
    const mains = shell.querySelectorAll('main');
    expect(mains).toHaveLength(1);
    const main = mains[0];
    expect(main.id).toBe('main');
    // Keeps the classes the page structure always had.
    expect(main.classList.contains('main')).toBe(true);
    expect(main.classList.contains('clearfix')).toBe(true);
    expect(main.querySelector('#root')).not.toBeNull();
    // No ARIA stand-in: axe only exempts page <header>s nested in a native <main>.
    expect(shell.querySelector('[role="main"]')).toBeNull();
  });

  it('keeps the three React roots and the chatbot root outside <main>', () => {
    for (const id of ['menu-root', 'footer-root', 'chatbot-root']) {
      const root = shell.getElementById(id);
      expect(root, id).not.toBeNull();
      expect(root?.closest('main'), id).toBeNull();
    }
  });

  it('takes the header and footer roots out of the layout on isolated routes', () => {
    mountShell({isolated: true});
    expect(getComputedStyle(document.getElementById('menu-root')!).display).toBe('none');
    expect(getComputedStyle(document.getElementById('footer-root')!).display).toBe('none');
  });

  it('shows neither the boot ring nor its label on isolated routes', () => {
    const hidden = new Set<string>();
    postcss.parse(inline).walkRules((rule) => {
      if (rule.some((node) => node.type === 'decl' && node.prop === 'display' && node.value === 'none')) {
        rule.selectors.forEach((selector) => hidden.add(selector));
      }
    });
    expect(hidden).toContain('html[data-block-preview] #root:empty::before');
    expect(hidden).toContain('html[data-block-preview] #root:empty::after');
  });

  it('leaves the header and footer roots alone on normal routes', () => {
    mountShell({isolated: false});
    expect(getComputedStyle(document.getElementById('menu-root')!).display).not.toBe('none');
    expect(getComputedStyle(document.getElementById('footer-root')!).display).not.toBe('none');
  });
});
