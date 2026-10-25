/// <reference types="node" />

import {readdirSync, readFileSync} from 'node:fs';
import {dirname, join, relative, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import postcss, {type AtRule, type Container, type Rule} from 'postcss';
import {describe, expect, it} from 'vitest';

// Bundled stylesheets load in import order, and route chunks load in navigation order, so a
// selector defined in two files gets whichever arrived last. Each selector has one owner. Files
// that one stylesheet @imports load together in a fixed order, so they share their importer's
// ownership (projects.css, for example, @imports the project page sections in cascade order).

const SRC_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const TESTS_DIR = join(SRC_DIR, '__tests__');

const listCss = (dir: string): string[] =>
  readdirSync(dir, {withFileTypes: true}).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (full === TESTS_DIR) return [];
    if (entry.isDirectory()) return listCss(full);
    return entry.name.endsWith('.css') ? [full] : [];
  });

const CSS_FILES = listCss(SRC_DIR).sort();

/** The stylesheet each file is @imported by (files imported by several, or by none, own themselves). */
const importers = new Map<string, Set<string>>();
for (const file of CSS_FILES) {
  postcss.parse(readFileSync(file, 'utf8'), {from: file}).walkAtRules('import', (atRule) => {
    const specifier = atRule.params.match(/^(?:url\(\s*)?['"]?([^'"()\s]+)/)?.[1];
    if (!specifier?.startsWith('.')) return;
    const target = resolve(dirname(file), specifier);
    if (!importers.has(target)) importers.set(target, new Set());
    importers.get(target)!.add(file);
  });
}

const ownerOf = (file: string): string => {
  const parents = importers.get(file);
  return parents?.size === 1 ? ownerOf([...parents][0]) : file;
};

// "owner file::selector" pairs allowed to repeat a selector owned elsewhere, each with its reason.
const SHARED_SELECTORS: Record<string, string> = {};

/** Splits an exception at its first "::"; the selector may hold one too (`.a::before`). */
const parseException = (entry: string) => {
  const separator = entry.indexOf('::');
  return {file: entry.slice(0, separator), key: entry.slice(separator + 2)};
};

const normalize = (text: string) => text.replace(/\s+/g, ' ').trim();

/** The @media / @supports / @layer chain a rule sits in, outermost first. */
const contextOf = (rule: Rule): string => {
  const chain: string[] = [];
  for (let parent: Container | undefined = rule.parent as Container | undefined; parent; parent = parent.parent as Container | undefined) {
    if (parent.type === 'atrule') {
      const atRule = parent as AtRule;
      chain.unshift(`@${atRule.name} ${normalize(atRule.params)}`);
    }
  }
  return chain.join(' > ');
};

/** One entry per selector of every style rule (keyframe steps excluded). */
const selectorsIn = (css: string, from: string) => {
  const entries: {key: string; selector: string}[] = [];
  postcss.parse(css, {from}).walkRules((rule) => {
    if (rule.parent?.type === 'atrule' && /keyframes$/i.test((rule.parent as AtRule).name)) return;
    const context = contextOf(rule);
    for (const selector of rule.selectors) {
      const normalized = normalize(selector);
      entries.push({key: `${context} ${normalized}`.trim(), selector: normalized});
    }
  });
  return entries;
};

describe('stylesheet parsing', () => {
  it.each(CSS_FILES.map((file) => [relative(SRC_DIR, file), file]))('%s parses', (_name, file) => {
    expect(() => postcss.parse(readFileSync(file, 'utf8'), {from: file})).not.toThrow();
  });
});

describe('selector ownership', () => {
  const owners = new Map<string, Set<string>>();
  for (const file of CSS_FILES) {
    const name = relative(SRC_DIR, ownerOf(file));
    for (const {key} of selectorsIn(readFileSync(file, 'utf8'), file)) {
      if (!owners.has(key)) owners.set(key, new Set());
      owners.get(key)!.add(name);
    }
  }

  it('no selector is defined in two stylesheets', () => {
    const repeated = [...owners.entries()]
      .filter(([, files]) => files.size > 1)
      .flatMap(([key, files]) => {
        const unexplained = [...files].filter((file) => !SHARED_SELECTORS[`${file}::${key}`]);
        return unexplained.length > 1 ? [`${key}  <-  ${[...files].sort().join(', ')}`] : [];
      });
    expect(repeated).toEqual([]);
  });

  it('every shared-selector exception is still needed', () => {
    const stale = Object.keys(SHARED_SELECTORS).filter((entry) => {
      const {file, key} = parseException(entry);
      return !(owners.get(key)?.has(file) && owners.get(key)!.size > 1);
    });
    expect(stale).toEqual([]);
  });
});

describe('ownership', () => {
  it('an @imported section belongs to the stylesheet that imports it', () => {
    const projects = join(SRC_DIR, 'features', 'projects', 'components');
    expect(ownerOf(join(projects, 'grid', 'gridTable.css'))).toBe(join(projects, 'projects.css'));
    expect(ownerOf(join(SRC_DIR, 'index.css'))).toBe(join(SRC_DIR, 'index.css'));
  });
});

describe('shared-selector exceptions', () => {
  it('keep a pseudo-element in the selector part', () => {
    expect(parseException('features/demo/Demo.css::@media (max-width: 992px) .a::before')).toEqual({
      file: 'features/demo/Demo.css',
      key: '@media (max-width: 992px) .a::before',
    });
  });
});

describe('selector scanner', () => {
  it('keys a selector by its at-rule context and ignores keyframe steps', () => {
    const css = [
      '.a, .b  .c { color: red; }',
      '@media (max-width: 992px) { .a { color: blue; } }',
      '@keyframes spin { from { opacity: 0; } to { opacity: 1; } }',
    ].join('\n');

    expect(selectorsIn(css, 'demo.css').map(({key}) => key)).toEqual(['.a', '.b .c', '@media (max-width: 992px) .a']);
  });
});
