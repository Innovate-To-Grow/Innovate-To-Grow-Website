

export const RICH_DETAIL_HIGHLIGHT_TAGS = new Set(['mark']);

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
