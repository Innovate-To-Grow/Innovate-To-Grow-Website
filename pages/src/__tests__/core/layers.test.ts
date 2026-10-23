/// <reference types="node" />

import {readdirSync, readFileSync} from 'node:fs';
import {dirname, join, relative, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import postcss, {type AtRule} from 'postcss';
import {describe, expect, it} from 'vitest';

import {COMPONENTS_LAYER, inComponentsLayer} from '@/lib/css';

// Layered rules lose to unlayered ones whatever their specificity, so one unlayered rule in the
// bundle would beat Site Settings' custom CSS (itg.overrides). Every bundled rule sits in a layer.

const SRC_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const PAGES_DIR = dirname(SRC_DIR);
const TESTS_DIR = join(SRC_DIR, '__tests__');
const LAYERS_FILE = join(SRC_DIR, 'styles', 'layers.css');

const listCss = (dir: string): string[] =>
  readdirSync(dir, {withFileTypes: true}).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (full === TESTS_DIR) return [];
    if (entry.isDirectory()) return listCss(full);
    return entry.name.endsWith('.css') ? [full] : [];
  });

const ALLOWED_LAYERS = new Set(['itg.defaults', COMPONENTS_LAYER]);
const normalize = (text: string) => text.replace(/\s+/g, ' ').trim();
const layerStatement = (css: string) => normalize(css.match(/@layer\s+[\w.\s,-]+;/)?.[0] ?? '');

describe('cascade layer order', () => {
  const declared = layerStatement(readFileSync(LAYERS_FILE, 'utf8'));

  it('names the six layers lowest first', () => {
    expect(declared).toBe('@layer itg.defaults, itg.tokens, itg.base, itg.components, itg.overrides, itg.page;');
  });

  it('opens the inline style of index.html with the same statement', () => {
    const html = readFileSync(join(PAGES_DIR, 'index.html'), 'utf8');
    const inlineStyle = html.match(/<style>([\s\S]*?)<\/style>/)?.[1] ?? '';
    const firstRule = postcss.parse(inlineStyle).nodes.find((node) => node.type !== 'comment');
    expect(firstRule?.type).toBe('atrule');
    expect(normalize(`@layer ${(firstRule as AtRule).params};`)).toBe(declared);
  });

  it('is the first stylesheet main.tsx imports', () => {
    const main = readFileSync(join(SRC_DIR, 'main.tsx'), 'utf8');
    expect(main.match(/^import\s+['"]([^'"]+\.css)['"]/m)?.[1]).toBe('./styles/layers.css');
  });
});

describe('every bundled rule is layered', () => {
  it.each(listCss(SRC_DIR).filter((file) => file !== LAYERS_FILE).map((file) => [relative(SRC_DIR, file), file]))(
    '%s',
    (_name, file) => {
      const strays = postcss
        .parse(readFileSync(file, 'utf8'), {from: file})
        .nodes.filter((node) => node.type !== 'comment')
        .filter((node) => {
          if (node.type !== 'atrule') return true;
          if (node.name === 'import') return false;
          return node.name !== 'layer' || !node.nodes || !ALLOWED_LAYERS.has(node.params.trim());
        })
        .map((node) => normalize(node.toString()).slice(0, 80));
      expect(strays).toEqual([]);
    },
  );
});

describe('runtime styles', () => {
  it('are wrapped in the components layer', () => {
    expect(inComponentsLayer('.a { color: red; }')).toBe('@layer itg.components {\n.a { color: red; }\n}');
  });
});
