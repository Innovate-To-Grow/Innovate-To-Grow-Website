// DOM helpers for the contentEditable rich-text note editor: stripping/unwrapping inline
// formatting, detecting and toggling <mark> highlight, and reading the live selection range.

export const RICH_DETAIL_FORMATTING_TAGS = new Set(['b', 'strong', 'i', 'em', 'u', 'mark', 'a', 'span', 'font']);
export const RICH_DETAIL_HIGHLIGHT_TAGS = new Set(['mark']);
export const RICH_DETAIL_INLINE_FORMAT_TAGS = {
  bold: new Set(['b', 'strong']),
  italic: new Set(['i', 'em']),
  underline: new Set(['u']),
};

const appendPlainFormattingNode = (target: DocumentFragment, node: Node) => {
  if (node.nodeType === Node.TEXT_NODE) {
    target.appendChild(document.createTextNode(node.textContent ?? ''));
    return;
  }

  if (node.nodeType !== Node.ELEMENT_NODE) {
    return;
  }

  const element = node as HTMLElement;
  const tagName = element.tagName.toLowerCase();

  if (tagName === 'br') {
    target.appendChild(document.createElement('br'));
    return;
  }

  Array.from(element.childNodes).forEach((child) => appendPlainFormattingNode(target, child));

  if (tagName === 'div' || tagName === 'p') {
    target.appendChild(document.createElement('br'));
  }
};

export const createPlainFormattingFragment = (source: DocumentFragment) => {
  const plainFragment = document.createDocumentFragment();
  Array.from(source.childNodes).forEach((node) => appendPlainFormattingNode(plainFragment, node));
  return plainFragment;
};

const insertedNodeRange = (nodes: Node[]) => ({
  firstInsertedNode: nodes[0] ?? null,
  lastInsertedNode: nodes.at(-1) ?? null,
});

const splitFormattingParentAroundMarker = (marker: HTMLElement, parentElement: Element) => {
  const parentNode = parentElement.parentNode;
  if (!parentNode) {
    return;
  }

  const before = parentElement.cloneNode(false);
  const after = parentElement.cloneNode(false);
  const hasContent = (node: Node) =>
    Array.from(node.childNodes).some((child) => child.nodeType !== Node.TEXT_NODE || child.textContent !== '');

  while (parentElement.firstChild && parentElement.firstChild !== marker) {
    before.appendChild(parentElement.firstChild);
  }

  while (marker.nextSibling) {
    after.appendChild(marker.nextSibling);
  }

  if (hasContent(before)) {
    parentNode.insertBefore(before, parentElement);
  }
  parentNode.insertBefore(marker, parentElement);
  if (hasContent(after)) {
    parentNode.insertBefore(after, parentElement);
  }
  parentNode.removeChild(parentElement);
};

const moveMarkerOutOfFormattingAncestors = (
  marker: HTMLElement,
  editor: HTMLElement,
  formattingTags = RICH_DETAIL_FORMATTING_TAGS,
) => {
  let parent = marker.parentNode;

  while (parent && parent !== editor) {
    if (parent.nodeType !== Node.ELEMENT_NODE) {
      return;
    }

    const parentElement = parent as Element;
    if (!formattingTags.has(parentElement.tagName.toLowerCase())) {
      return;
    }

    splitFormattingParentAroundMarker(marker, parentElement);
    parent = marker.parentNode;
  }
};

export const replaceRangeWithPlainFormatting = (range: Range, editor: HTMLElement) => {
  const marker = document.createElement('span');
  marker.appendChild(createPlainFormattingFragment(range.extractContents()));
  range.insertNode(marker);
  moveMarkerOutOfFormattingAncestors(marker, editor);

  const insertedNodes = Array.from(marker.childNodes);
  marker.replaceWith(...insertedNodes);

  return insertedNodeRange(insertedNodes);
};

export const replaceRangeWithoutMatchingFormatting = (
  range: Range,
  editor: HTMLElement,
  formattingTags: Set<string>,
) => {
  const fragment = range.extractContents();
  unwrapMatchingElements(fragment, formattingTags);

  const marker = document.createElement('span');
  marker.appendChild(fragment);
  range.insertNode(marker);
  moveMarkerOutOfFormattingAncestors(marker, editor, formattingTags);

  const insertedNodes = Array.from(marker.childNodes);
  marker.replaceWith(...insertedNodes);

  return insertedNodeRange(insertedNodes);
};

export const wrapRangeWithFormatting = (range: Range, tagName: string) => {
  const wrapper = document.createElement(tagName);
  wrapper.appendChild(range.extractContents());
  range.insertNode(wrapper);

  return insertedNodeRange([wrapper]);
};

export const replaceEditorWithPlainFormatting = (editor: HTMLElement) => {
  const range = document.createRange();
  range.selectNodeContents(editor);

  const plainFragment = createPlainFormattingFragment(range.cloneContents());
  const insertedNodes = Array.from(plainFragment.childNodes);
  editor.replaceChildren(plainFragment);

  return insertedNodeRange(insertedNodes);
};

const unwrapElement = (element: Element) => {
  const parent = element.parentNode;
  if (!parent) {
    return;
  }

  while (element.firstChild) {
    parent.insertBefore(element.firstChild, element);
  }
  parent.removeChild(element);
};

export const unwrapMatchingElements = (root: ParentNode, tags: Set<string>) => {
  const selector = Array.from(tags).join(',');
  root.querySelectorAll(selector).forEach(unwrapElement);
};

export const clearInsertedFormattingAncestors = (
  node: Node,
  editor: HTMLElement,
  formattingTags = RICH_DETAIL_FORMATTING_TAGS,
) => {
  let current = node.nodeType === Node.ELEMENT_NODE ? node : node.parentNode;

  while (current && current !== editor) {
    const parent = current.parentNode;
    if (current.nodeType === Node.ELEMENT_NODE) {
      const element = current as Element;
      if (formattingTags.has(element.tagName.toLowerCase())) {
        unwrapElement(element);
      }
    }
    current = parent;
  }
};

const nodeHasFormatting = (node: Node, editor: HTMLElement, formattingTags: Set<string>) => {
  let current = node.nodeType === Node.ELEMENT_NODE ? node : node.parentNode;

  while (current && current !== editor) {
    if (current.nodeType === Node.ELEMENT_NODE && formattingTags.has((current as Element).tagName.toLowerCase())) {
      return true;
    }
    current = current.parentNode;
  }

  return false;
};

export const rangeContainsFormatting = (range: Range, editor: HTMLElement, formattingTags: Set<string>) => {
  const selector = Array.from(formattingTags).join(',');
  if (selector && range.cloneContents().querySelector(selector)) {
    return true;
  }

  return (
    nodeHasFormatting(range.startContainer, editor, formattingTags) ||
    nodeHasFormatting(range.endContainer, editor, formattingTags)
  );
};

export const rangeContainsHighlight = (range: Range, editor: HTMLElement) =>
  rangeContainsFormatting(range, editor, RICH_DETAIL_HIGHLIGHT_TAGS);

export const getEditorSelectionRange = (editor: HTMLElement) => {
  const selection = window.getSelection();
  if (!selection || !selection.rangeCount || !selection.anchorNode || !selection.focusNode) {
    return null;
  }

  const ownsNode = (node: Node) => node === editor || editor.contains(node);
  if (!ownsNode(selection.anchorNode) || !ownsNode(selection.focusNode)) {
    return null;
  }

  const range = selection.getRangeAt(0);
  return range.collapsed ? null : range;
};
