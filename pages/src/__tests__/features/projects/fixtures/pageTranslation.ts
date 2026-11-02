/**
 * What browser page translation (Chrome's Translate) does to a rendered page: every text node with words in it is
 * replaced by <font><font>translated text</font></font>, and the original node is left detached. React still holds
 * the detached nodes, so a component that updates or removes one writes to (or removes) a node that is no longer
 * in the page. The marker stands in for the translation, so a test can strip it and read what the page says.
 */
export const TRANSLATION_MARKER = '[ES]';

export function translatePage(root: Element) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  nodes.forEach((node) => {
    if (!node.nodeValue?.trim() || !node.parentNode) return;
    const outer = document.createElement('font');
    const inner = document.createElement('font');
    inner.textContent = `${TRANSLATION_MARKER}${node.nodeValue}`;
    outer.appendChild(inner);
    node.parentNode.replaceChild(outer, node);
  });
}

/** The text an element shows, without the translation markers. */
export const shownText = (element: Element | null) =>
  (element?.textContent ?? '').split(TRANSLATION_MARKER).join('');
