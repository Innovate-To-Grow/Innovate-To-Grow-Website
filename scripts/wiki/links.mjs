import { parse, postprocess, preprocess } from 'micromark';
import { gfm } from 'micromark-extension-gfm';
import { decodeString } from 'micromark-util-decode-string';

const repositoryRoot = 'https://repository.invalid/';
const destinationTokens = new Set(['resourceDestinationString', 'definitionDestinationString']);

export function encodePath(path) {
  return path.split('/').map(part => encodeURIComponent(part)
    .replaceAll('(', '%28').replaceAll(')', '%29')).join('/');
}

function rewriteDestination(destination, source, repository) {
  const { url, pages, directories, files } = repository;
  const raw = decodeString(destination);
  const mainUrl = [url + '/blob/main/', url + '/tree/main/'].find(prefix => raw.startsWith(prefix));
  if (!mainUrl && /^(?:[a-z][a-z\d+.-]*:|\/\/|#|\?)/i.test(raw)) return destination;

  const local = mainUrl ? repositoryRoot + raw.slice(mainUrl.length) : raw;
  const target = new URL(local, repositoryRoot + encodePath(source));
  if (target.origin + '/' !== repositoryRoot) return destination;
  const encoded = target.pathname.slice(1).replace(/%(?![0-9a-f]{2})/gi, '%25');
  const path = decodeURIComponent(encoded).replace(/\/$/, '');
  const page = pages.get(path) ?? pages.get(path + '/index.md') ?? pages.get(path + '/README.md');
  if (page && !target.search) return url + '/wiki/' + page + target.hash;

  // GitHub's blob view supports ?raw=true for image links as well as the normal file view.
  const view = directories.has(path) ? 'tree' : 'blob';
  const suffix = target.search + target.hash;
  if (!path) return url + '/' + suffix;
  if (view === 'blob' && !files.has(path)) repository.missing.add(source + ' -> ' + path);
  return url + '/' + view + '/main/' + encodePath(path) + suffix;
}

export function rewriteLinks(markdown, source, repository) {
  const input = markdown.replace(/^\uFEFF/, '');
  const chunks = preprocess()(input, 'utf8', true);
  const events = postprocess(parse({ extensions: [gfm()] }).document().write(chunks));
  const output = [];
  let cursor = 0;
  for (const [event, token] of events) {
    if (event !== 'enter' || !destinationTokens.has(token.type)) continue;
    const start = token.start.offset;
    const end = token.end.offset;
    output.push(input.slice(cursor, start), rewriteDestination(input.slice(start, end), source, repository));
    cursor = end;
  }
  return output.join('') + input.slice(cursor);
}
