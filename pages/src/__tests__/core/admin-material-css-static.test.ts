/// <reference types="node" />

import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import {describe, expect, it} from 'vitest';

/**
 * The admin's Material theme (src/apps/core/static/admin/css/google-material-admin.css) repaints every
 * `bg-white` / `dark:bg-base-900` element as a surface, with !important. Unfold's radio and checkbox inputs carry
 * those same classes and show their checked state through `checked:bg-primary-600`, so the surface rules must
 * leave form controls alone: with them included, a selected "Email format" radio looked unselected.
 */

const testDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(testDir, '../../../..');
const css = readFileSync(resolve(repoRoot, 'src/apps/core/static/admin/css/google-material-admin.css'), 'utf8');

function surfaceSelectors(): string[] {
  const selectors: string[] = [];
  for (const match of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const [, selector, body] = match;
    if (/--md-sys-color-surface-container(?:-lowest)?\)\s*!important/.test(body) && selector.includes('bg-white')) {
      selectors.push(selector.trim());
    }
  }
  return selectors;
}

function control(type: string, className: string, dark = false): Element {
  document.body.innerHTML = `<div class="${dark ? 'dark' : ''}"><input type="${type}" class="${className}"></div>`;
  return document.querySelector('input') as Element;
}

describe('google-material-admin.css surface rules', () => {
  const selectors = surfaceSelectors();

  it('has a light and a dark surface rule for bg-white elements', () => {
    expect(selectors).toHaveLength(2);
  });

  it.each(['radio', 'checkbox'])('leave an Unfold %s input alone in both themes', (type) => {
    for (const selector of selectors) {
      expect(control(type, 'appearance-none bg-white checked:bg-primary-600').matches(selector)).toBe(false);
      expect(control(type, 'appearance-none dark:bg-base-900', true).matches(selector)).toBe(false);
    }
  });

  it('still repaint panels and cards', () => {
    document.body.innerHTML = '<div class="dark"><div class="rounded-default bg-white dark:bg-base-900"></div></div>';
    const panel = document.querySelector('div.bg-white') as Element;
    for (const selector of selectors) {
      expect(panel.matches(selector)).toBe(true);
    }
  });
});
