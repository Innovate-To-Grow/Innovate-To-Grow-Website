/// <reference types="node" />

import {existsSync, readdirSync, readFileSync} from 'node:fs';
import {dirname, join, relative, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import {describe, expect, it} from 'vitest';

// Every stylesheet in the app (the test tree excluded), loaded lazily by Vite.
const CSS_MODULES = import.meta.glob(['/src/**/*.css', '!/src/__tests__/**']);

const SRC_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const PAGES_DIR = dirname(SRC_DIR);
const TESTS_DIR = join(SRC_DIR, '__tests__');

const listFiles = (dir: string): string[] =>
  readdirSync(dir, {withFileTypes: true}).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (full === TESTS_DIR) return [];
    return entry.isDirectory() ? listFiles(full) : [full];
  });

const SOURCE_FILES = listFiles(SRC_DIR);
const CSS_FILES = SOURCE_FILES.filter((file) => file.endsWith('.css')).sort();
// A stylesheet only a test imports is not used by the app, so test modules never count as importers.
const APP_MODULES = SOURCE_FILES.filter((file) => /\.tsx?$/.test(file) && !/\.test\.tsx?$/.test(file));

const fromPages = (file: string) => relative(PAGES_DIR, file);

// `import './x.css'`, `import styles from './x.module.css'` (line-anchored, so commented-out imports
// do not count) and `import('./x.css')`. A `?inline` / `?url` query is part of the specifier, not the path.
const MODULE_CSS_IMPORTS = [
  /^\s*import\s+(?:[^'";]*?\s+from\s+)?['"]([^'"]+?\.css)(?:\?[^'"]*)?['"]/gm,
  /\bimport\(\s*['"]([^'"]+?\.css)(?:\?[^'"]*)?['"]\s*\)/g,
];
// `@import './x.css';`, `@import "./x.css";` and `@import url('./x.css');`
const CSS_AT_IMPORT = /@import\s+(?:url\(\s*)?['"]?([^'"()\s;]+?\.css)(?:\?[^'"()\s;]*)?['"]?/g;

const stripCssComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, '');

/** The CSS specifiers a module (or, for `isCss`, a stylesheet's `@import`s) pulls in. */
const cssSpecifiersIn = (source: string, isCss: boolean): string[] => {
  const patterns = isCss ? [CSS_AT_IMPORT] : MODULE_CSS_IMPORTS;
  const text = isCss ? stripCssComments(source) : source;
  return patterns.flatMap((pattern) => Array.from(text.matchAll(pattern), (match) => match[1]));
};

/** Absolute path of a `./`, `../` or `@/` CSS specifier; null for package CSS (node_modules). */
const resolveCssSpecifier = (fromFile: string, specifier: string): string | null => {
  if (specifier.startsWith('@/')) return join(SRC_DIR, specifier.slice(2));
  if (specifier.startsWith('./') || specifier.startsWith('../')) return resolve(dirname(fromFile), specifier);
  return null;
};

const CSS_IMPORTS = [...APP_MODULES, ...CSS_FILES].flatMap((from) =>
  cssSpecifiersIn(readFileSync(from, 'utf8'), from.endsWith('.css')).map((specifier) => ({
    from,
    specifier,
    target: resolveCssSpecifier(from, specifier),
  })),
);

describe('CSS imports resolve', () => {
  it('main entry CSS resolves', async () => {
    await expect(import('@/index.css')).resolves.toBeDefined();
  });

  it('the import glob sees exactly the stylesheets on disk', () => {
    const globbed = Object.keys(CSS_MODULES).map((key) => join(PAGES_DIR, key)).sort();
    expect(globbed.map(fromPages)).toEqual(CSS_FILES.map(fromPages));
  });

  it.each(Object.entries(CSS_MODULES))('%s resolves when imported', async (_path, load) => {
    await expect(load()).resolves.toBeDefined();
  });
});

describe('CSS import scanner', () => {
  const importer = join(SRC_DIR, 'features', 'demo', 'Demo.tsx');

  it('reads static, dynamic and query-suffixed imports from a module', () => {
    const source = [
      "import './Demo.css';",
      'import styles from "../shared/demo.module.css";',
      "import inline from '@/assets/inline.css?inline';",
      "const lazy = () => import('./lazy.css');",
      "// import './commented-out.css';",
      "import {helper} from './helper';",
    ].join('\n');

    expect(cssSpecifiersIn(source, false)).toEqual([
      './Demo.css',
      '../shared/demo.module.css',
      '@/assets/inline.css',
      './lazy.css',
    ]);
  });

  it('reads every @import form from a stylesheet and ignores commented-out ones', () => {
    const css = [
      "@import './a.css';",
      '@import "../b.css";',
      "@import url('@/c.css');",
      '@import url(./d.css);',
      "/* @import './commented-out.css'; */",
      '.rule { color: red; }',
    ].join('\n');

    expect(cssSpecifiersIn(css, true)).toEqual(['./a.css', '../b.css', '@/c.css', './d.css']);
  });

  it('resolves ./, ../ and @/ specifiers to absolute paths and skips package CSS', () => {
    expect(resolveCssSpecifier(importer, './Demo.css')).toBe(join(SRC_DIR, 'features', 'demo', 'Demo.css'));
    expect(resolveCssSpecifier(importer, '../shared/x.css')).toBe(join(SRC_DIR, 'features', 'shared', 'x.css'));
    expect(resolveCssSpecifier(importer, '@/assets/tokens.css')).toBe(join(SRC_DIR, 'assets', 'tokens.css'));
    expect(resolveCssSpecifier(importer, 'some-package/dist/style.css')).toBeNull();
  });
});

describe('every stylesheet is used', () => {
  it('finds the stylesheets it checks', () => {
    expect(CSS_FILES.map(fromPages)).toEqual(
      expect.arrayContaining(['src/index.css', 'src/assets/tokens.css', 'src/app/MaintenanceMode/MaintenanceMode.css']),
    );
  });

  it('every CSS import points at a file that exists', () => {
    const broken = CSS_IMPORTS.filter(({target}) => target !== null && !existsSync(target));
    expect(broken.map(({from, specifier}) => `${fromPages(from)} -> ${specifier}`)).toEqual([]);
  });

  it('every CSS file is imported by a module or by an @import in another stylesheet', () => {
    const imported = new Set(CSS_IMPORTS.flatMap(({from, target}) => (target && target !== from ? [target] : [])));
    const orphans = CSS_FILES.filter((file) => !imported.has(file));
    expect(orphans.map(fromPages)).toEqual([]);
  });
});

describe('maintenance page styles are bundled with the app', () => {
  // The maintenance page is shown when the backend is down, and the backend also serves
  // /api/layout/styles.css, so the page must never depend on that sheet.
  const maintenanceDir = join(SRC_DIR, 'app', 'MaintenanceMode');
  const maintenanceCss = stripCssComments(readFileSync(join(maintenanceDir, 'MaintenanceMode.css'), 'utf8'));

  /** Declarations of the top-level rule whose whole selector is `selector`. */
  const ruleBody = (selector: string) => {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\-]/g, '\\$&');
    return maintenanceCss.match(new RegExp(String.raw`(?:^|\})\s*${escaped}\s*\{([^}]*)\}`, 'm'))?.[1];
  };

  it('MaintenanceMode.tsx imports ./MaintenanceMode.css', () => {
    const source = readFileSync(join(maintenanceDir, 'MaintenanceMode.tsx'), 'utf8');
    expect(source).toMatch(/^import\s+['"]\.\/MaintenanceMode\.css['"];?\s*$/m);
  });

  it.each([
    ['.maintenance-container', /position:\s*fixed/],
    ['.maintenance-bar', /background:\s*var\(--itg-color-primary\)/],
    ['.service-degraded-banner', /background:\s*var\(--itg-color-highlight\)/],
  ])('MaintenanceMode.css defines %s', (selector, declaration) => {
    const body = ruleBody(selector);
    expect(body, `${selector} { ... } is missing`).toBeDefined();
    expect(body).toMatch(declaration);
  });

  it('every --itg- token it reads without a fallback is defined in the bundled tokens.css', () => {
    const tokensCss = readFileSync(join(SRC_DIR, 'assets', 'tokens.css'), 'utf8');
    const defined = new Set(Array.from(tokensCss.matchAll(/(--itg-[\w-]+)\s*:/g), (match) => match[1]));
    const required = new Set(Array.from(maintenanceCss.matchAll(/var\(\s*(--itg-[\w-]+)\s*\)/g), (match) => match[1]));

    expect(required.size).toBeGreaterThan(0);
    expect([...required].filter((token) => !defined.has(token))).toEqual([]);
  });
});
