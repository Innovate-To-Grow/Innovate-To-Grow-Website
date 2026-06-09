// DOM helpers for the contentEditable rich-text note editor: stripping/unwrapping inline
// formatting, detecting and toggling <mark> highlight, and reading the live selection range.

export const RICH_DETAIL_FORMATTING_TAGS = new Set(['b', 'strong', 'i', 'em', 'u', 'mark', 'a', 'span', 'font']);
export const RICH_DETAIL_HIGHLIGHT_TAGS = new Set(['mark']);

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

const nodeHasHighlight = (node: Node, editor: HTMLElement) => {
  let current = node.nodeType === Node.ELEMENT_NODE ? node : node.parentNode;

  while (current && current !== editor) {
    if (current.nodeType === Node.ELEMENT_NODE && (current as Element).tagName.toLowerCase() === 'mark') {
      return true;
    }
    current = current.parentNode;
  }

  return false;
};

export const rangeContainsHighlight = (range: Range, editor: HTMLElement) => {
  if (range.cloneContents().querySelector('mark')) {
    return true;
  }

  return nodeHasHighlight(range.startContainer, editor) || nodeHasHighlight(range.endContainer, editor);
};

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
