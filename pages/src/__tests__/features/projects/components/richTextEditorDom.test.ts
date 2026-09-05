import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  clearInsertedFormattingAncestors,
  createPlainFormattingFragment,
  getEditorSelectionRange,
  rangeContainsFormatting,
  rangeContainsHighlight,
  replaceEditorWithPlainFormatting,
  replaceRangeWithPlainFormatting,
  replaceRangeWithoutMatchingFormatting,
  unwrapMatchingElements,
  wrapRangeWithFormatting,
} from '@/features/projects/components/richTextEditorDom';

function makeEditor(html: string): HTMLElement {
  const editor = document.createElement('div');
  editor.contentEditable = 'true';
  editor.innerHTML = html;
  document.body.appendChild(editor);
  return editor;
}

function rangeForText(root: Node, text: string): Range {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node: Node | null;
  while ((node = walker.nextNode())) {
    const idx = (node.textContent ?? '').indexOf(text);
    if (idx !== -1) {
      const range = document.createRange();
      range.setStart(node, idx);
      range.setEnd(node, idx + text.length);
      return range;
    }
  }
  throw new Error(`text "${text}" not found`);
}

afterEach(() => {
  document.body.innerHTML = '';
  vi.restoreAllMocks();
});

describe('createPlainFormattingFragment', () => {
  it('flattens inline formatting into plain text plus block breaks', () => {
    const editor = makeEditor('<p>Hello <b>world</b>!</p>');
    const range = document.createRange();
    range.selectNodeContents(editor);

    const plain = createPlainFormattingFragment(range.cloneContents());
    const holder = document.createElement('div');
    holder.appendChild(plain);

    expect(holder.textContent).toBe('Hello world!');
    expect(holder.querySelector('b')).toBeNull();
    expect(holder.querySelector('br')).not.toBeNull();
  });
});

describe('replaceEditorWithPlainFormatting', () => {
  it('replaces all editor content with flattened text', () => {
    const editor = makeEditor('<p><b>bold</b> text</p>');

    replaceEditorWithPlainFormatting(editor);

    expect(editor.textContent).toBe('bold text');
    expect(editor.querySelector('b')).toBeNull();
  });
});

describe('unwrapMatchingElements', () => {
  it('unwraps matching tags but leaves others intact', () => {
    const editor = makeEditor('<div><b>a</b><i>b</i></div>');

    unwrapMatchingElements(editor, new Set(['b']));

    expect(editor.querySelector('b')).toBeNull();
    expect(editor.querySelector('i')).not.toBeNull();
  });
});

describe('clearInsertedFormattingAncestors', () => {
  it('unwraps formatting ancestors up to the editor boundary', () => {
    const editor = makeEditor('<b><span id="x">text</span></b>');
    const span = editor.querySelector('#x')!;

    clearInsertedFormattingAncestors(span, editor);

    expect(editor.querySelector('b')).toBeNull();
    expect(editor.textContent).toBe('text');
  });
});

describe('rangeContainsFormatting', () => {
  it('detects formatting via an ancestor of the selection', () => {
    const editor = makeEditor('<p><b>bold</b> plain</p>');

    expect(rangeContainsFormatting(rangeForText(editor, 'bold'), editor, new Set(['b', 'strong']))).toBe(true);
    expect(rangeContainsFormatting(rangeForText(editor, 'plain'), editor, new Set(['b', 'strong']))).toBe(false);
  });
});

describe('rangeContainsHighlight', () => {
  it('detects a mark highlight in the selection', () => {
    const editor = makeEditor('<p><mark>hi</mark></p>');

    expect(rangeContainsHighlight(rangeForText(editor, 'hi'), editor)).toBe(true);
  });
});

describe('replaceRangeWithPlainFormatting', () => {
  it('replaces a formatted selection with plain text', () => {
    const editor = makeEditor('<p>Hello <b>world</b>!</p>');

    replaceRangeWithPlainFormatting(rangeForText(editor, 'world'), editor);

    expect(editor.textContent).toBe('Hello world!');
    expect(editor.querySelector('b')).toBeNull();
  });
});

describe('replaceRangeWithoutMatchingFormatting', () => {
  it('removes a specific formatting tag around the selection', () => {
    const editor = makeEditor('<p><b>bold</b> and <i>italic</i></p>');

    replaceRangeWithoutMatchingFormatting(rangeForText(editor, 'bold'), editor, new Set(['b']));

    expect(editor.textContent).toContain('bold');
    expect(editor.querySelector('b')).toBeNull();
  });
});

describe('wrapRangeWithFormatting', () => {
  it('wraps the selection in the requested tag', () => {
    const editor = makeEditor('<p>hello</p>');

    wrapRangeWithFormatting(rangeForText(editor, 'hello'), 'mark');

    expect(editor.querySelector('mark')?.textContent).toBe('hello');
  });
});

describe('getEditorSelectionRange', () => {
  it('returns null when there is no selection', () => {
    vi.spyOn(window, 'getSelection').mockReturnValue(null);
    expect(getEditorSelectionRange(makeEditor('<p>x</p>'))).toBeNull();
  });

  it('returns null when the selection has no range', () => {
    vi.spyOn(window, 'getSelection').mockReturnValue({rangeCount: 0} as Selection);
    expect(getEditorSelectionRange(makeEditor('<p>x</p>'))).toBeNull();
  });

  it('returns null when the anchor is outside the editor', () => {
    const editor = makeEditor('<p>x</p>');
    const outside = document.createElement('div');
    document.body.appendChild(outside);

    vi.spyOn(window, 'getSelection').mockReturnValue({
      rangeCount: 1,
      anchorNode: outside,
      focusNode: editor,
      getRangeAt: () => ({collapsed: false}),
    } as unknown as Selection);

    expect(getEditorSelectionRange(editor)).toBeNull();
  });

  it('returns null for a collapsed range', () => {
    const editor = makeEditor('<p>x</p>');
    vi.spyOn(window, 'getSelection').mockReturnValue({
      rangeCount: 1,
      anchorNode: editor,
      focusNode: editor,
      getRangeAt: () => ({collapsed: true}),
    } as unknown as Selection);

    expect(getEditorSelectionRange(editor)).toBeNull();
  });

  it('returns the non-collapsed selection range', () => {
    const editor = makeEditor('<p>x</p>');
    const range = document.createRange();
    range.selectNodeContents(editor);

    vi.spyOn(window, 'getSelection').mockReturnValue({
      rangeCount: 1,
      anchorNode: editor.firstChild,
      focusNode: editor.firstChild,
      getRangeAt: () => range,
    } as unknown as Selection);

    expect(getEditorSelectionRange(editor)).toBe(range);
  });
});
