import { execFileSync } from 'node:child_process';
import { readFileSync, readdirSync, unlinkSync, writeFileSync } from 'node:fs';
import { join, posix } from 'node:path';
import { pathToFileURL } from 'node:url';
import { rewriteLinks } from './links.mjs';

const generated = '<!-- Managed by the docs-to-wiki workflow. -->\n';
const categories = new Map([
  ['architecture', 'Architecture'],
  ['deployment', 'Deployment'],
  ['operations', 'Operations'],
  ['staff', 'Staff Handbook'],
  ['api', 'API'],
  ['cms-admin', 'CMS & Admin'],
  ['integrations', 'Integrations'],
  ['standards', 'Standards'],
]);

function displayName(name) {
  return name.replaceAll(/(^|[-_])(\w)/g, (_, gap, letter) => (gap ? ' ' : '') + letter.toUpperCase());
}

function wikiPage(path) {
  return path.slice(0, -3).split('/').map(segment => (
    segment.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  )).join('--');
}

function loadRepository(url) {
  const entries = execFileSync('git', ['ls-files', '--stage', '-z'], { encoding: 'utf8' })
    .split('\0').filter(Boolean);
  const files = new Set();
  const directories = new Set();
  const pages = new Map();
  const pageNames = new Set();
  for (const entry of entries) {
    const separator = entry.indexOf('\t');
    const path = entry.slice(separator + 1);
    files.add(path);
    for (let parent = posix.dirname(path); parent !== '.'; parent = posix.dirname(parent)) {
      directories.add(parent);
    }
    if (!path.startsWith('docs/') || !/\.md$/i.test(path)) continue;
    if (!entry.startsWith('100')) throw new Error('Expected a tracked Markdown file: ' + path);
    const page = wikiPage(path);
    if (pageNames.has(page)) throw new Error('Duplicate Wiki page name for ' + path + ': ' + page);
    pages.set(path, page);
    pageNames.add(page);
  }
  return { url, pages, directories, files, missing: new Set() };
}

function docTitle(source, markdown) {
  const heading = markdown.trimStart().match(/^#\s+([^\r\n]+?)\s*$/m)?.[1] ?? displayName(posix.basename(source, '.md'));
  return heading.replaceAll(/[[\]]/g, '\\$&');
}

function homePage(url, groups) {
  const lines = [
    'Documentation for the Innovate To Grow website at the UC Merced School of Engineering.',
    '',
    'These pages are published from [the repository documentation](' + url + '/tree/main/docs).',
    'To update a page, edit its source Markdown file in the repository.',
    '',
  ];
  const sections = new Set([...categories.keys(), ...groups.keys()]);
  for (const category of sections) {
    if (!groups.has(category)) continue;
    lines.push('## ' + (categories.get(category) ?? displayName(category)), '', ...groups.get(category), '');
  }
  lines.push('[Project README](' + url + '/blob/main/README.md)', '');
  return generated + lines.join('\n');
}

function renderPages(repository) {
  const results = new Map();
  const groups = new Map();
  for (const [source, page] of repository.pages) {
    const markdown = readFileSync(source, 'utf8');
    results.set(page + '.md', generated + rewriteLinks(markdown, source, repository));

    const category = source.split('/')[2] ? source.split('/')[1] : 'General';
    const links = groups.get(category) ?? [];
    const link = '- [' + docTitle(source, markdown) + '](' + repository.url + '/wiki/' + page + ')';
    if (posix.dirname(source) === 'docs/' + category && /\/(index|readme)\.md$/i.test(source)) {
      links.unshift(link);
    } else {
      links.push(link);
    }
    groups.set(category, links);
  }
  results.set('Home.md', homePage(repository.url, groups));
  return results;
}

function updateWiki(wikiDirectory, results) {
  const existing = readdirSync(wikiDirectory, { withFileTypes: true });
  const managed = new Set(existing.filter(entry => entry.isFile() && /^docs--.*\.md$/.test(entry.name))
    .filter(entry => readFileSync(join(wikiDirectory, entry.name), 'utf8').startsWith(generated))
    .map(entry => entry.name));
  for (const entry of existing) {
    if (!results.has(entry.name)) continue;
    if (!entry.isFile() || (entry.name !== 'Home.md' && !managed.has(entry.name))) {
      throw new Error('Wiki page conflicts with a generated page: ' + entry.name);
    }
  }
  for (const [filename, markdown] of results) {
    writeFileSync(join(wikiDirectory, filename), markdown);
  }
  for (const stale of managed) {
    if (!results.has(stale)) unlinkSync(join(wikiDirectory, stale));
  }
}

export function syncWiki(wikiDirectory, repositoryUrl) {
  const repository = loadRepository(repositoryUrl);
  const results = renderPages(repository);
  if (repository.missing.size) {
    throw new Error('Broken repository links in docs/:\n' + [...repository.missing].join('\n'));
  }
  updateWiki(wikiDirectory, results);
  return repository.pages.size;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  const [, , wikiDirectory, repositoryUrl] = process.argv;
  if (!wikiDirectory || !repositoryUrl) throw new Error('Usage: node sync.mjs <wiki checkout> <repository URL>');
  console.log('Prepared the Wiki home page and ' + syncWiki(wikiDirectory, repositoryUrl) + ' documentation pages.');
}
