/// <reference types="node" />

import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import postcss, {type AtRule, type Container} from 'postcss';
import {afterEach, describe, expect, it} from 'vitest';

/** A file under pages/src, read from this test's place in it. */
const readSource = (path: string) => readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../..', path), 'utf8');

const indexHtml = readSource('../index.html');
const shell = new DOMParser().parseFromString(indexHtml, 'text/html');
const inline = Array.from(shell.head.querySelectorAll('style'), (node) => node.textContent).join('\n');
const indicatorCss = readSource('components/LoadingIndicator/LoadingIndicator.css');
const containerCss = readSource('features/layout/components/Container/Container.css');
const tokensCss = readSource('assets/tokens.css');

/** The declarations of the first rule written exactly `selector {`. */
const declarations = (css: string, selector: string): Record<string, string> => {
  const body = css.slice(css.indexOf(`${selector} {`)).match(/\{([^}]*)\}/)?.[1] ?? '';
  return Object.fromEntries(
    body
      .split(';')
      .map((declaration) => {
        const colon = declaration.indexOf(':');
        return [declaration.slice(0, colon).trim(), declaration.slice(colon + 1).trim().replace(/\s+/g, ' ')];
      })
      .filter(([property, value]) => property && value),
  );
};

/** The boot rules run before any token sheet, so they add fallbacks that the bundled rules leave out. */
const withoutFallbacks = (value: string) => value.replace(/var\((--[\w-]+), [^)]+\)/g, 'var($1)');

/** A CSS string's text, with its escapes (such as `\2026`) decoded. */
const cssText = (value: string) =>
  value.slice(1, -1).replace(/\\([0-9a-f]{1,6}) ?/gi, (_, hex: string) => String.fromCodePoint(parseInt(hex, 16)));

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

  it('draws the boot spinner as the ring of the shared loading indicator', () => {
    // The first paint, the lazy-route fallback and the pages' loading lines show one spinner, so a cold load never
    // swaps a big ring for a small one.
    const boot = declarations(inline, '#root:empty::before');
    const spinner = declarations(indicatorCss, '.loading-indicator-spinner');

    for (const property of ['box-sizing', 'width', 'height', 'border', 'border-top-color', 'border-radius']) {
      expect(withoutFallbacks(boot[property] ?? ''), property).toBe(spinner[property]);
    }
    const turn = (animation: string) => animation.match(/-spin (\S+) linear infinite/)?.[1];
    expect(turn(boot.animation)).toBe(turn(spinner.animation));
    expect(turn(spinner.animation)).toBe('0.8s');
  });

  it("puts the boot ring and its label where the lazy-route fallback's appear, so nothing jumps", () => {
    // The fallback (router.tsx routeFallback, Container.tsx) centres the indicator in .page-loader, under the page
    // shell's top padding; #root starts at the same place before and after React mounts the shell into it.
    const shellPaddingTops = [...containerCss.matchAll(/\.app-layout \{[^}]*?padding: (\S+)/g)].map((match) => match[1]);
    const loaderHeight = declarations(containerCss, '.page-loader')['min-height'];
    const ringSize = declarations(indicatorCss, '.loading-indicator-spinner').height;
    expect(new Set(shellPaddingTops), 'the shell keeps one top padding at every width').toEqual(new Set(['16px']));
    expect(loaderHeight).toBe('50vh');
    const top = `calc(${shellPaddingTops[0]} + (${loaderHeight} - ${ringSize}) / 2)`;

    const ring = declarations(inline, '#root:empty::before');
    const label = declarations(inline, '#root:empty::after');
    expect(ring['margin-top']).toBe(top);
    expect(label['margin-top']).toBe(top);
    expect(ring.margin).toBeUndefined();

    // The same label, gap and text style as the fallback's indicator.
    const fallbackLabels = ['app/router/router.tsx', 'features/layout/components/Container/Container.tsx'].map(
      (path) => readSource(path).match(/className="page-loader"[^>]*>\s*<LoadingIndicator label="([^"]+)"/)?.[1],
    );
    expect(fallbackLabels).toEqual(['Loading…', 'Loading…']);
    expect(cssText(label.content)).toBe('Loading…');
    const indicator = declarations(indicatorCss, '.loading-indicator');
    expect(label['margin-left']).toBe(indicator.gap);
    for (const property of ['color', 'font-size', 'line-height']) {
      expect(withoutFallbacks(label[property] ?? ''), property).toBe(indicator[property]);
    }
  });

  it('gives every token in the boot ring and label a fallback, since they paint before any token sheet loads', () => {
    for (const selector of ['#root:empty::before', '#root:empty::after']) {
      for (const [property, value] of Object.entries(declarations(inline, selector))) {
        for (const use of value.match(/var\([^)]*\)/g) ?? []) {
          expect(use, `${selector} ${property}`).toMatch(/^var\(--[\w-]+, .+\)$/);
        }
      }
    }
  });

  it("falls back to each token's default in assets/tokens.css, so the boot ring paints the colours the page will", () => {
    // The defaults: the custom properties of tokens.css's top-level :root, outside any media query.
    const defaults = new Map<string, string>();
    postcss.parse(tokensCss).walkRules(':root', (rule) => {
      for (let parent = rule.parent as Container | undefined; parent; parent = parent.parent as Container | undefined) {
        if (parent.type === 'atrule' && (parent as AtRule).name !== 'layer') return;
      }
      rule.walkDecls(/^--itg-/, (decl) => void defaults.set(decl.prop, decl.value));
    });
    // Case- and shorthand-insensitive: #DDD, #ddd and #dddddd are one colour.
    const normalise = (value: string) =>
      value
        .trim()
        .toLowerCase()
        .replace(/\s+/g, ' ')
        .replace(/^#([0-9a-f])([0-9a-f])([0-9a-f])([0-9a-f])?$/, (_, r, g, b, a = '') => `#${r}${r}${g}${g}${b}${b}${a}${a}`);

    const fallbacks: string[] = [];
    postcss.parse(inline).walkRules((rule) => {
      if (!rule.selectors.some((selector) => ['#root:empty::before', '#root:empty::after'].includes(selector))) return;
      rule.walkDecls((decl) => {
        for (const [, token, fallback] of decl.value.matchAll(/var\((--[\w-]+),\s*([^)]+)\)/g)) {
          fallbacks.push(token);
          expect(defaults.has(token), `${token} is a token in tokens.css`).toBe(true);
          expect(normalise(fallback), `${rule.selector} ${decl.prop}: ${token}`).toBe(normalise(defaults.get(token) ?? ''));
        }
      });
    });
    expect(fallbacks.length, 'the boot ring and label use tokens').toBeGreaterThan(0);
  });

  it('keeps the scrollbar gutter free while the boot ring shows, so the ring does not move sideways', () => {
    // The fallback's page is taller than the screen, so where scrollbars take up width it has one and the boot page
    // (one screen tall) would not; the reserved gutter puts both rings in the same centred column.
    const gutterRules: string[] = [];
    postcss.parse(inline).walkRules((rule) => {
      rule.walkDecls('scrollbar-gutter', (decl) => {
        // Unlayered (top level), like the row rule, so nothing in the bundle outranks it.
        gutterRules.push(`${rule.parent?.type} ${rule.selector} ${decl.value}`);
      });
    });
    expect(gutterRules).toEqual(['root html:has(#root:empty) stable']);
  });

  it('lays the boot ring and label out in a row that outranks the bundle and keeps its motion and contrast rules', () => {
    const root = postcss.parse(inline);
    const rowRules = root.nodes.filter((node) => node.type === 'rule' && node.selector === '#root:empty');
    // Unlayered: a rule in the lowest layer would lose to the bundle's #root column (itg.components).
    expect(rowRules).toHaveLength(1);
    expect(declarations(inline, '#root:empty')).toEqual({
      display: 'flex',
      'flex-direction': 'row',
      'align-items': 'flex-start',
      'justify-content': 'center',
    });

    const mediaRules = (query: string) => {
      const found: Record<string, string> = {};
      root.walkAtRules('media', (atRule: AtRule) => {
        if (atRule.params !== query) return;
        atRule.walkRules('#root:empty::before', (rule) => rule.walkDecls((decl) => void (found[decl.prop] = decl.value)));
      });
      return found;
    };
    expect(mediaRules('(prefers-reduced-motion: reduce)')).toEqual({
      animation: 'itg-init-loader-fade-in 0.25s ease-out',
      opacity: '0.7',
    });
    expect(mediaRules('(forced-colors: active)')).toEqual({
      'forced-color-adjust': 'none',
      'border-color': 'GrayText',
      'border-top-color': 'CanvasText',
    });
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
