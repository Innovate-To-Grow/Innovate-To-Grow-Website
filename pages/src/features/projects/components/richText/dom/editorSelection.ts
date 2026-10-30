import {
  RICH_DETAIL_HIGHLIGHT_TAGS,
  clearInsertedFormattingAncestors,
  unwrapMatchingElements,
} from './richTextEditorDom';

/** Whether the range starts and ends inside the editor. */
export const rangeBelongsToEditor = (range: Range, editor: HTMLElement) => {
  const ownsNode = (node: Node) => node === editor || editor.contains(node);
  return ownsNode(range.startContainer) && ownsNode(range.endContainer);
};

const replaceSelection = (selection: Selection, nextRange: Range) => {
  selection.removeAllRanges();
  selection.addRange(nextRange);
};

/** Select from before ``firstNode`` to after ``lastNode``; the new range, or null when nothing was selected. */
export const selectAroundNodes = (firstNode: Node | null, lastNode: Node | null): Range | null => {
  if (!firstNode || !lastNode) {
    return null;
  }
  const selection = window.getSelection();
  if (!selection) {
    return null;
  }
  const nextRange = document.createRange();
  nextRange.setStartBefore(firstNode);
  nextRange.setEndAfter(lastNode);
  replaceSelection(selection, nextRange);
  return nextRange;
};

/** Put the caret right after ``node``; false when there is no node or selection to move. */
export const collapseAfterNode = (node: Node | null): boolean => {
  const selection = window.getSelection();
  if (!node || !selection) {
    return false;
  }
  const nextRange = document.createRange();
  nextRange.setStartAfter(node);
  nextRange.collapse(true);
  replaceSelection(selection, nextRange);
  return true;
};

/** Unwrap every highlight inside the range, leaving the caret after the change. */
export const removeHighlightInRange = (range: Range, editor: HTMLElement) => {
  const selection = window.getSelection();
  const fragment = range.extractContents();
  unwrapMatchingElements(fragment, RICH_DETAIL_HIGHLIGHT_TAGS);
  const insertedNodes = Array.from(fragment.childNodes);
  const lastInsertedNode = insertedNodes.at(-1) ?? null;
  range.insertNode(fragment);
  insertedNodes.forEach((node) => clearInsertedFormattingAncestors(node, editor, RICH_DETAIL_HIGHLIGHT_TAGS));

  if (lastInsertedNode && selection) {
    const nextRange = document.createRange();
    nextRange.setStartAfter(lastInsertedNode);
    nextRange.collapse(true);
    replaceSelection(selection, nextRange);
  }
};

/** Wrap the range in one <mark> and select its contents. */
export const highlightRange = (range: Range) => {
  const selection = window.getSelection();
  const fragment = range.extractContents();
  // Strip any nested highlight so toggling never yields <mark><mark>…</mark></mark>.
  unwrapMatchingElements(fragment, RICH_DETAIL_HIGHLIGHT_TAGS);
  const mark = document.createElement('mark');
  mark.appendChild(fragment);
  range.insertNode(mark);

  // Re-select the highlighted content so an immediate second click toggles it back off
  // (getEditorSelectionRange returns null for a collapsed selection). Wrapping a real <mark>
  // ourselves — instead of execCommand('hiliteColor'), which emits a background-color span —
  // keeps the live DOM, the stored value, and the highlight detection all in agreement.
  if (selection) {
    const nextRange = document.createRange();
    nextRange.selectNodeContents(mark);
    replaceSelection(selection, nextRange);
  }
};
