/// <reference types="node" />

import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import postcss, {type AtRule, type Container, type Root} from 'postcss';
import {describe, expect, it} from 'vitest';

// .home-loading is a content class (contract-classes.json): stored body_html can use it, so it keeps its own rules in
// styles/contract/. It draws the same loading look as the LoadingIndicator component; these checks keep the copy in step.

const SRC_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const parse = (path: string): Root => postcss.parse(readFileSync(resolve(SRC_DIR, path), 'utf8'), {from: path});

const home = parse('styles/contract/page-home.css');
const indicator = parse('components/LoadingIndicator/LoadingIndicator.css');

/** The @media a rule sits in ('' outside any), ignoring the cascade layer every file wraps itself in. */
const mediaOf = (container: Container | undefined): string => {
  for (let parent = container; parent; parent = parent.parent as Container | undefined) {
    if (parent.type === 'atrule' && (parent as AtRule).name === 'media') return (parent as AtRule).params;
  }
  return '';
};

/** A selector's declarations, per @media, merged in source order. */
const declarations = (root: Root, selector: string): Record<string, Record<string, string>> => {
  const byMedia: Record<string, Record<string, string>> = {};
  root.walkRules((rule) => {
    if (!rule.selectors.includes(selector)) return;
    const media = mediaOf(rule.parent as Container);
    byMedia[media] ??= {};
    rule.walkDecls((decl) => {
      byMedia[media][decl.prop] = decl.value;
    });
  });
  return byMedia;
};

const ring = declarations(home, '.home-loading::before');
const spinner = declarations(indicator, '.loading-indicator-spinner');
const line = declarations(home, '.home-loading')[''];
const indicatorLine = declarations(indicator, '.loading-indicator')[''];

/** "itg-spin 0.8s linear infinite" without its keyframes name, which each file defines for itself. */
const timing = (animation: string) => animation.split(/\s+/).slice(1).join(' ');

describe('.home-loading (page-home.css)', () => {
  it('draws the 24px ring of LoadingIndicator', () => {
    for (const property of ['content', 'box-sizing', 'flex', 'width', 'height', 'border', 'border-top-color', 'border-radius']) {
      expect(ring[''][property], property).toBe(property === 'content' ? "''" : spinner[''][property]);
    }
    expect(spinner[''].width).toBe('24px');
    expect(timing(ring[''].animation)).toBe(timing(spinner[''].animation));
  });

  it('spins with keyframes that the contract stylesheets define', () => {
    const name = ring[''].animation.split(/\s+/)[0];
    const contract = parse('styles/contract/global/notices.css');
    const turns: string[] = [];
    contract.walkAtRules('keyframes', (atRule) => {
      if (atRule.params === name) atRule.walkDecls('transform', (decl) => void turns.push(decl.value));
    });
    expect(turns).toEqual(['rotate(360deg)']);
  });

  it('sets its text in the LoadingIndicator type, beside the ring', () => {
    for (const property of ['gap', 'color', 'font-size', 'line-height']) {
      expect(line[property], property).toBe(indicatorLine[property]);
    }
    expect(line['align-items']).toBe('center');
    expect(line['flex-direction']).toBeUndefined();
    expect(line['font-style']).toBeUndefined();
    // The line keeps the room it reserved before.
    expect(line['min-height']).toBe('40vh');
  });

  it('stops, keeps its contrast and leaves print as LoadingIndicator does', () => {
    const media = ['(prefers-reduced-motion: reduce)', '(forced-colors: active)', 'print'];
    for (const query of media) {
      expect(spinner[query], query).toBeDefined();
      expect(ring[query], query).toEqual(spinner[query]);
    }
    expect(Object.keys(ring).sort()).toEqual(['', ...media].sort());
  });
});
