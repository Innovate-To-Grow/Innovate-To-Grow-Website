import {sanitizePastProjectsDetailHtml} from '../pastProjectsDetailText';

/** A run of text carrying the inline emphasis the rich editor supports. */
export interface StyledRun {
  text: string;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  highlight?: boolean;
}

interface ActiveStyle {
  bold: boolean;
  italic: boolean;
  underline: boolean;
  highlight: boolean;
}

const EMPHASIS_TAGS: Record<string, keyof ActiveStyle> = {
  b: 'bold',
  strong: 'bold',
  i: 'italic',
  em: 'italic',
  u: 'underline',
  mark: 'highlight',
};

const BLOCK_TAGS = new Set(['div', 'p']);

const pushText = (runs: StyledRun[], text: string, style: ActiveStyle) => {
  if (!text) {
    return;
  }
  const previous = runs.at(-1);
  // Merge consecutive runs that share styling so downstream formats emit fewer nodes.
  if (
    previous &&
    !previous.text.endsWith('\n') &&
    Boolean(previous.bold) === style.bold &&
    Boolean(previous.italic) === style.italic &&
    Boolean(previous.underline) === style.underline &&
    Boolean(previous.highlight) === style.highlight
  ) {
    previous.text += text;
    return;
  }
  runs.push({
    text,
    ...(style.bold ? {bold: true} : {}),
    ...(style.italic ? {italic: true} : {}),
    ...(style.underline ? {underline: true} : {}),
    ...(style.highlight ? {highlight: true} : {}),
  });
};

const pushLineBreak = (runs: StyledRun[]) => {
  const previous = runs.at(-1);
  if (previous) {
    previous.text += '\n';
  } else {
    runs.push({text: '\n'});
  }
};

const walk = (node: Node, style: ActiveStyle, runs: StyledRun[]) => {
  if (node.nodeType === Node.TEXT_NODE) {
    // contentEditable encodes spacing as &nbsp; — normalize back to a regular space for export.
    pushText(runs, (node.textContent ?? '').replace(/\u00a0/g, ' '), style);
    return;
  }

  if (node.nodeType !== Node.ELEMENT_NODE) {
    return;
  }

  const element = node as HTMLElement;
  const tag = element.tagName.toLowerCase();

  if (tag === 'br') {
    pushLineBreak(runs);
    return;
  }

  const emphasis = EMPHASIS_TAGS[tag];
  const nextStyle: ActiveStyle = emphasis ? {...style, [emphasis]: true} : style;

  // A block element starts on its own line when it follows existing content.
  if (BLOCK_TAGS.has(tag) && runs.length && !(runs.at(-1)?.text.endsWith('\n') ?? false)) {
    pushLineBreak(runs);
  }

  Array.from(element.childNodes).forEach((child) => walk(child, nextStyle, runs));

  if (BLOCK_TAGS.has(tag) && runs.length && !(runs.at(-1)?.text.endsWith('\n') ?? false)) {
    pushLineBreak(runs);
  }
};

const collapseTrailingBlankRuns = (runs: StyledRun[]): StyledRun[] => {
  const trimmed = [...runs];
  while (trimmed.length) {
    const last = trimmed[trimmed.length - 1];
    last.text = last.text.replace(/\n+$/, '');
    if (last.text) {
      break;
    }
    trimmed.pop();
  }
  return trimmed;
};

/**
 * Parse a row's sanitized rich-text curation note into styled runs (bold/italic/underline/
 * highlight, with `\n` line breaks). Returns [] for an empty note. Falls back to a single plain
 * run when no DOM is available (non-browser test envs) so callers always get usable text.
 */
export const parseRichTextRuns = (html: string): StyledRun[] => {
  const sanitized = sanitizePastProjectsDetailHtml(html ?? '');
  if (!sanitized.trim()) {
    return [];
  }

  if (typeof document === 'undefined') {
    const plain = sanitized
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/(div|p)>/gi, '\n')
      .replace(/<[^>]*>/g, '')
      .replace(/\u00a0/g, ' ')
      .replace(/\n{3,}/g, '\n\n')
      .trimEnd();
    return plain ? [{text: plain}] : [];
  }

  const template = document.createElement('template');
  template.innerHTML = sanitized;
  const runs: StyledRun[] = [];
  const baseStyle: ActiveStyle = {bold: false, italic: false, underline: false, highlight: false};
  Array.from(template.content.childNodes).forEach((child) => walk(child, baseStyle, runs));
  return collapseTrailingBlankRuns(runs);
};

/** Flatten styled runs back to plain text (used where only text matters, e.g. emptiness checks). */
export const runsToPlainText = (runs: StyledRun[]) => runs.map((run) => run.text).join('');
