/// <reference types="node" />

import {readdirSync, readFileSync} from 'node:fs';
import {dirname, join, relative, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import postcss, {type AtRule, type Container, type Rule} from 'postcss';
import {describe, expect, it} from 'vitest';

// Every pager on the site (projects lists, News, the event archive tables, CMS content) is one look: the buttons
// of styles/contract/global/pagination.css. A page may lay its pager out (alignment, gaps, which parts show) but
// never redraw the buttons, and phones.css alone restates their size at 992px and below (44px targets).

const SRC_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..');
const TESTS_DIR = join(SRC_DIR, '__tests__');
const PAGER_CSS = 'styles/contract/global/pagination.css';
const PHONES_CSS = 'styles/contract/global/phones.css';

const listFiles = (dir: string, pattern: RegExp): string[] =>
  readdirSync(dir, {withFileTypes: true}).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (full === TESTS_DIR) return [];
    if (entry.isDirectory()) return listFiles(full, pattern);
    return pattern.test(entry.name) ? [full] : [];
  });

const CSS_FILES = listFiles(SRC_DIR, /\.css$/).sort();
const sourcePath = (file: string) => relative(SRC_DIR, file);

/** The classes the pager's buttons carry: .itg-pagination-link and every class written beside it in the markup. */
const PAGER_BUTTON_CLASSES = (() => {
  const classes = new Set(['itg-pagination-link']);
  for (const file of listFiles(SRC_DIR, /\.tsx?$/)) {
    for (const match of readFileSync(file, 'utf8').matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\})/g)) {
      const tokens = (match[1] ?? match[2]).split(/\s+/);
      if (!tokens.includes('itg-pagination-link')) continue;
      tokens.filter((token) => /^[\w-]+$/.test(token)).forEach((token) => classes.add(token));
    }
  }
  return classes;
})();

/** Properties that draw the button rather than place it. */
const isLookProperty = (prop: string) =>
  /^(background|border|outline|box-shadow)/.test(prop) || ['color', 'min-width', 'min-height'].includes(prop);

/** The @media / @supports / @layer chain a rule sits in, outermost first. */
const contextOf = (rule: Rule): string[] => {
  const chain: string[] = [];
  for (let parent = rule.parent as Container | undefined; parent; parent = parent.parent as Container | undefined) {
    if (parent.type === 'atrule') chain.unshift(`@${(parent as AtRule).name} ${(parent as AtRule).params}`);
  }
  return chain;
};

/** The classes of the element a selector styles: its last compound, with :is()/:has() arguments and attributes left out. */
const subjectClasses = (selector: string): string[] => {
  let flat = selector.replace(/\[[^\]]*\]/g, '[]');
  while (/\([^()]*\)/.test(flat)) flat = flat.replace(/\([^()]*\)/g, '');
  const compounds = flat.trim().split(/\s*[>+~]\s*|\s+/);
  return [...(compounds[compounds.length - 1] ?? '').matchAll(/\.([\w-]+)/g)].map((match) => match[1]);
};

interface PagerDeclaration {
  file: string;
  context: string[];
  selector: string;
  prop: string;
  value: string;
}

/** Every look declaration on a pager button, in every bundled stylesheet. */
const PAGER_LOOK = CSS_FILES.flatMap((file) => {
  const found: PagerDeclaration[] = [];
  postcss.parse(readFileSync(file, 'utf8'), {from: file}).walkRules((rule) => {
    if (rule.parent?.type === 'atrule' && /keyframes$/i.test((rule.parent as AtRule).name)) return;
    const selectors = rule.selectors.filter((selector) =>
      subjectClasses(selector).some((name) => PAGER_BUTTON_CLASSES.has(name)),
    );
    if (selectors.length === 0) return;
    rule.walkDecls((decl) => {
      if (!isLookProperty(decl.prop)) return;
      for (const selector of selectors) {
        found.push({file: sourcePath(file), context: contextOf(rule), selector, prop: decl.prop, value: decl.value});
      }
    });
  });
  return found;
});

describe('the site pager', () => {
  it('finds the pager buttons in the projects, News and event archive markup', () => {
    // The classes each pager writes beside .itg-pagination-link, so a page cannot redraw its buttons through them.
    for (const name of ['project-grid-pager-step', 'project-grid-pager-page', 'news-pagination-page', 'sdt-page-btn']) {
      expect(PAGER_BUTTON_CLASSES, name).toContain(name);
    }
  });

  it('draws its buttons in pagination.css only', () => {
    const elsewhere = PAGER_LOOK.filter(({file, context, prop}) => {
      if (file === PAGER_CSS) return false;
      // phones.css restates the 44px target size, and nothing else.
      const phoneSize = file === PHONES_CSS && context.includes('@media (max-width: 992px)');
      return !(phoneSize && ['min-width', 'min-height'].includes(prop));
    });
    expect(elsewhere.map(({file, selector, prop, value}) => `${file} ${selector} { ${prop}: ${value} }`)).toEqual([]);
  });

  it('is a 40px outline button that phones.css alone raises to 44px at 992px and below', () => {
    const base = (prop: string) =>
      PAGER_LOOK.find(
        (entry) =>
          entry.file === PAGER_CSS &&
          entry.selector === '.itg-pagination-link' &&
          entry.prop === prop &&
          !entry.context.some((at) => at.startsWith('@media')),
      )?.value;
    expect(base('min-width')).toBe('40px');
    expect(base('min-height')).toBe('40px');
    expect(base('border')).toBe('2px solid var(--itg-color-primary)');
    expect(base('background')).toBe('var(--itg-color-white)');

    const sizes = PAGER_LOOK.filter(({prop, context}) =>
      ['min-width', 'min-height'].includes(prop) && context.some((at) => at.startsWith('@media')),
    );
    expect(sizes.map(({file, context, selector, prop, value}) => [file, context.at(-1), selector, prop, value])).toEqual([
      [PHONES_CSS, '@media (max-width: 992px)', '.itg-pagination-link', 'min-height', '44px'],
      [PHONES_CSS, '@media (max-width: 992px)', '.itg-pagination-link', 'min-width', '44px'],
    ]);
  });

  it('fills only the current page, and marks it in the selection colours under forced colours', () => {
    const current = PAGER_LOOK.filter(({selector}) => selector === ".itg-pagination-link[aria-current='page']");
    const plain = current.filter(({context}) => !context.some((at) => at.startsWith('@media')));
    expect(Object.fromEntries(plain.map(({prop, value}) => [prop, value]))).toMatchObject({
      background: 'var(--itg-color-primary)',
      color: 'var(--itg-color-white)',
    });
    const forced = current.filter(({context}) => context.includes('@media (forced-colors: active)'));
    expect(Object.fromEntries(forced.map(({prop, value}) => [prop, value]))).toEqual({
      'border-color': 'Highlight',
      background: 'Highlight',
      color: 'HighlightText',
    });
  });

  it('prints only its "Page x of y", so a printed page says it holds one page of the rows', () => {
    // [selector, display] for every display rule in a media query that applies to print.
    const printDisplay = (path: string) => {
      const found: [string, string][] = [];
      postcss.parse(readFileSync(join(SRC_DIR, path), 'utf8')).walkAtRules('media', (atRule) => {
        if (!atRule.params.split(',').some((query) => query.trim() === 'print')) return;
        atRule.walkRules((rule) =>
          rule.walkDecls('display', (decl) => rule.selectors.forEach((selector) => found.push([selector, decl.value]))),
        );
      });
      return found;
    };
    // The buttons and the gaps between the numbers leave the paper; the page line stays.
    expect(printDisplay(PAGER_CSS)).toEqual([
      ['.itg-pagination-link', 'none'],
      ['.itg-pagination-gap', 'none'],
    ]);
    // No page takes the pager or its page line off the paper, except the projects lists (below).
    const keptOnPaper = new Set(['itg-pagination', 'itg-pagination-info', 'news-pagination', 'news-pagination-info', 'sdt-pagination', 'sdt-page-info']);
    const hidden = CSS_FILES.flatMap((file) =>
      printDisplay(sourcePath(file))
        .filter(([selector, value]) => value === 'none' && subjectClasses(selector).some((name) => keptOnPaper.has(name)))
        .map(([selector]) => `${sourcePath(file)} ${selector}`),
    );
    expect(hidden).toEqual([]);

    // News shows its page line, visually hidden on wide screens, on paper as it does on phones, in place of the numbers.
    const shownFor: string[] = [];
    postcss.parse(readFileSync(join(SRC_DIR, 'routes/NewsPage/NewsPage.css'), 'utf8')).walkRules('.news-pagination-info', (rule) => {
      if (rule.some((node) => node.type === 'decl' && node.prop === 'position' && node.value === 'static')) {
        shownFor.push((rule.parent as AtRule).params);
      }
    });
    expect(shownFor).toEqual(['(max-width: 768px), print']);
    expect(printDisplay('routes/NewsPage/NewsPage.css')).toContainEqual(['.news-pagination-pages', 'none']);

    // The projects lists' status line says which rows they show ("showing 1–10"), so their pager leaves the paper whole.
    expect(printDisplay('features/projects/components/styles/cascade/projectsResponsive.css')).toContainEqual([
      '.project-grid-pagination',
      'none',
    ]);
  });
});
