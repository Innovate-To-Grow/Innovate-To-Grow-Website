/// <reference types="node" />
// Helpers for the tests that run Django admin static scripts and template scripts in jsdom (window.eval).

import {existsSync, readdirSync, readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../..');

/** A file of the repository, by its path from the repository root. */
export const readRepoFile = (path: string): string => readFileSync(resolve(repoRoot, path), 'utf8');

/** Where Django finds a template name: the including app's templates first, then every app's. */
const templateFile = (name: string, root: string): string => {
  const roots = [root, ...readdirSync(resolve(repoRoot, 'src/apps')).map((app) => `src/apps/${app}/templates/`)];
  const found = roots.find((dir) => existsSync(resolve(repoRoot, dir + name)));
  if (!found) throw new Error(`template ${name} not found`);
  return found + name;
};

/**
 * A Django template as it renders: each line that is only `{% include "name" %}` is replaced by that template
 * (its leading `{% load %}`, which renders nothing, dropped), so scripts split into included parts read whole.
 */
export function readTemplate(path: string): string {
  const root = path.slice(0, path.indexOf('/templates/') + '/templates/'.length);
  return readRepoFile(path).replace(/^\{% include "([^"]+)" %\}$/gm, (_line, name: string) =>
    readTemplate(templateFile(name, root)).replace(/^\{% load [\w ]+ %\}/, '').replace(/\n$/, ''),
  );
}

const substitute = (text: string, vars: Record<string, string>) =>
  text.replace(/\{\{\s*([^}|\s]+)[^}]*\}\}/g, (_match, name: string) => vars[name] ?? '');

/** The HTML inside `{% block <block> %}` of a Django template, without its scripts or template tags. */
export function templateMarkup(path: string, block: string, vars: Record<string, string> = {}): string {
  const source = readTemplate(path);
  const start = source.indexOf(`{% block ${block} %}`);
  if (start < 0) throw new Error(`${path} has no block ${block}`);
  const body = source.slice(start + `{% block ${block} %}`.length, source.lastIndexOf('{% endblock %}'));
  return substitute(body.replace(/<script[\s\S]*?<\/script>/g, ''), vars).replace(/\{%[\s\S]*?%\}/g, '');
}

/** The inline (nonce) scripts of a Django template, with `{{ name }}` replaced from `vars`. */
export function inlineScripts(path: string, vars: Record<string, string> = {}): string[] {
  const source = readTemplate(path);
  return [...source.matchAll(/<script nonce="[^"]*">([\s\S]*?)<\/script>/g)].map((match) => substitute(match[1], vars));
}

/** The shared admin poll back-off (admin/js/poll-backoff.js), installed as window.I2GPollBackoff. */
export const installPollBackoff = () => window.eval(readRepoFile('src/apps/core/static/admin/js/poll-backoff.js'));

/** A fetch Response with a JSON body. */
export const jsonResponse = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), {status, headers: {'Content-Type': 'application/json', ...headers}});

/** Let pending promise callbacks (a fetch chain) run without moving the fake clock. */
export const flush = async (rounds = 10) => {
  for (let index = 0; index < rounds; index += 1) await Promise.resolve();
};
