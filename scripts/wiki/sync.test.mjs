import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { rewriteLinks } from './links.mjs';

const url = 'https://github.com/example/project';

test('rewrites Markdown links, definitions and repository files without changing examples', () => {
  const markdown = [
    '| Doc |',
    '| --- |',
    '| [Guide](../deployment/index.md#build) |',
    '',
    '[Read][guide] [Files](../deployment/) [Source](../../README.md#documentation)',
    '[External](https://example.com) [Here](#local) [Repo link](' + url + '/blob/main/docs/deployment/index.md)',
    '',
    '[guide]: <../deployment/index.md#build> "Guide"',
    '',
    '\x60[Inline example](missing.md)\x60',
    '',
    '\x60\x60\x60markdown',
    '[Fenced example](missing.md)',
    '\x60\x60\x60',
    '',
  ].join('\n');
  const repository = {
    url,
    pages: new Map([['docs/deployment/index.md', 'docs--deployment--index']]),
    files: new Set(['README.md']),
    directories: new Set(['docs/deployment']),
    missing: new Set(),
  };
  const page = url + '/wiki/docs--deployment--index';
  assert.equal(rewriteLinks(markdown, 'docs/staff/README.md', repository), markdown
    .replaceAll('../deployment/index.md#build', page + '#build')
    .replace('../deployment/', page)
    .replace('../../README.md#documentation', url + '/blob/main/README.md#documentation')
    .replace(url + '/blob/main/docs/deployment/index.md', page));
  assert.equal(repository.missing.size, 0);
});

test('refreshes the English index and removes only previously generated pages', t => {
  const root = mkdtempSync(join(tmpdir(), 'wiki-sync-test-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const wiki = join(root, 'wiki');
  mkdirSync(wiki);
  const git = (...args) => execFileSync('git', args, { cwd: root });
  const sync = () => execFileSync(process.execPath, [
    fileURLToPath(new URL('./sync.mjs', import.meta.url)), wiki, url,
  ], { cwd: root });
  const read = path => readFileSync(join(wiki, path), 'utf8');
  const add = (path, content) => {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), content);
    git('add', path);
  };

  git('init', '-q');
  add('docs/architecture/backend.md', '# Backend Architecture\n\n[Deployment](../deployment/backend.md#build)\n');
  add('docs/deployment/backend.md', '# Backend Deployment\n\n## Build\n');
  writeFileSync(join(wiki, 'Home.md'), 'Old home');
  writeFileSync(join(wiki, 'Manual.md'), 'Hand-written page');
  sync();

  assert.match(read('Home.md'), /## Architecture\n\n- \[Backend Architecture\]/);
  assert.match(read('Home.md'), /## Deployment\n\n- \[Backend Deployment\]/);
  assert.ok(read('docs--architecture--backend.md').includes(url + '/wiki/docs--deployment--backend#build'));
  const home = read('Home.md');
  sync();
  assert.equal(read('Home.md'), home);

  git('rm', '-f', 'docs/architecture/backend.md');
  sync();
  assert.doesNotMatch(read('Home.md'), /## Architecture/);
  assert.equal(read('Manual.md'), 'Hand-written page');
  assert.deepEqual(readdirSync(wiki).sort(), ['Home.md', 'Manual.md', 'docs--deployment--backend.md']);
});
