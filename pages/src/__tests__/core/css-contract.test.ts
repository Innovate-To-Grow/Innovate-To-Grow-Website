/// <reference types="node" />

import {readdirSync, readFileSync} from 'node:fs';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import postcss from 'postcss';
import {describe, expect, it} from 'vitest';

import contract from '@/styles/contract/contract-classes.json';

// Stored CMS content carries these classes, and no deploy can change what is stored. A class in
// the contract keeps at least one rule in styles/contract/ (which ships in the entry bundle, so
// every CMS page has it); dropping one needs a production content audit first.

const CONTRACT_DIR = join(resolve(dirname(fileURLToPath(import.meta.url)), '../..'), 'styles', 'contract');

const listCss = (dir: string): string[] =>
  readdirSync(dir, {withFileTypes: true}).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) return listCss(full);
    return entry.name.endsWith('.css') ? [full] : [];
  });

const CONTRACT_SELECTORS = listCss(CONTRACT_DIR).flatMap((file) => {
  const selectors: string[] = [];
  postcss.parse(readFileSync(file, 'utf8'), {from: file}).walkRules((rule) => {
    selectors.push(rule.selector);
  });
  return selectors;
});

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const isStyled = (className: string) => {
  const pattern = new RegExp(`\\.${escapeRegExp(className)}(?![\\w-])`);
  return CONTRACT_SELECTORS.some((selector) => pattern.test(selector));
};

describe('content contract', () => {
  const groups = {content_html: contract.content_html, design_system: contract.design_system};

  it.each(Object.entries(groups))('lists %s classes once, in order', (_group, classes) => {
    expect(classes.length).toBeGreaterThan(0);
    expect(classes).toEqual([...new Set(classes)].sort());
  });

  it.each(Object.entries(groups))('keeps a rule for every %s class in styles/contract/', (_group, classes) => {
    expect(classes.filter((className) => !isStyled(className))).toEqual([]);
  });

  it('matches a class only as a whole token', () => {
    expect(isStyled('itg-btn')).toBe(true);
    expect(isStyled('itg-bt')).toBe(false);
  });
});
