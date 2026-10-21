import {useRef, type ClipboardEvent, type MouseEvent, type RefObject} from 'react';
import {
  RICH_DETAIL_INLINE_FORMAT_TAGS,
  getEditorSelectionRange,
  rangeContainsFormatting,
  rangeContainsHighlight,
  replaceRangeWithoutMatchingFormatting,
  replaceEditorWithPlainFormatting,
  replaceRangeWithPlainFormatting,
  wrapRangeWithFormatting,
} from './richTextEditorDom';
import {collapseAfterNode, highlightRange, rangeBelongsToEditor, removeHighlightInRange, selectAroundNodes} from './editorSelection';

export type InlineFormat = keyof typeof RICH_DETAIL_INLINE_FORMAT_TAGS;

/**
 * The editor's last selection: toolbar clicks take focus from the editor, so commands fall back to the
 * range remembered before the click.
 */
function useEditorSelectionMemory(editorRef: RefObject<HTMLDivElement | null>) {
  const lastSelectionRangeRef = useRef<Range | null>(null);

  const rememberSelectionRange = () => {
    const editor = editorRef.current;
    if (!editor) {
      return;
    }

    const range = getEditorSelectionRange(editor);
    if (range) {
      lastSelectionRangeRef.current = range.cloneRange();
    }
  };

  const getActiveEditorRange = (editor: HTMLElement) => {
    const currentRange = getEditorSelectionRange(editor);
    if (currentRange) {
      lastSelectionRangeRef.current = currentRange.cloneRange();
      return currentRange;
    }

    const savedRange = lastSelectionRangeRef.current;
    if (savedRange && !savedRange.collapsed && rangeBelongsToEditor(savedRange, editor)) {
      return savedRange.cloneRange();
    }

    return null;
  };

  const restoreSelectionAroundNodes = (firstNode: Node | null, lastNode: Node | null) => {
    const nextRange = selectAroundNodes(firstNode, lastNode);
    if (nextRange) {
      lastSelectionRangeRef.current = nextRange.cloneRange();
    }
  };

  const collapseSelectionAfterNode = (node: Node | null) => {
    if (collapseAfterNode(node)) {
      lastSelectionRangeRef.current = null;
    }
  };

  return {rememberSelectionRange, getActiveEditorRange, restoreSelectionAroundNodes, collapseSelectionAfterNode};
}

/**
 * The editor's formatting commands. Toolbar clicks take focus from the editor, so the last selection
 * inside it is remembered and the command applies to that; each command re-selects what it changed
 * (or collapses after it) and emits the sanitized markup.
 */
export function useRichTextFormatting(
  editorRef: RefObject<HTMLDivElement | null>,
  readOnly: boolean,
  emitChange: () => void,
) {
  const {rememberSelectionRange, getActiveEditorRange, restoreSelectionAroundNodes, collapseSelectionAfterNode} =
    useEditorSelectionMemory(editorRef);

  const handleToolbarMouseDown = (event: MouseEvent<HTMLButtonElement>) => {
    rememberSelectionRange();
    event.preventDefault();
  };

  const applyInlineFormat = (format: InlineFormat, tagName: string) => {
    if (readOnly || !editorRef.current) {
      return;
    }

    const editor = editorRef.current;
    const range = getActiveEditorRange(editor);
    if (!range) {
      editor.focus();
      return;
    }

    const formattingTags = RICH_DETAIL_INLINE_FORMAT_TAGS[format];
    const {firstInsertedNode, lastInsertedNode} = rangeContainsFormatting(range, editor, formattingTags)
      ? replaceRangeWithoutMatchingFormatting(range, editor, formattingTags)
      : wrapRangeWithFormatting(range, tagName);
    restoreSelectionAroundNodes(firstInsertedNode, lastInsertedNode);
    editor.focus();
    emitChange();
  };

  const clearFormatting = () => {
    if (readOnly || !editorRef.current) {
      return;
    }

    const editor = editorRef.current;
    const range = getActiveEditorRange(editor);
    const {lastInsertedNode} = range
      ? replaceRangeWithPlainFormatting(range, editor)
      : replaceEditorWithPlainFormatting(editor);

    collapseSelectionAfterNode(lastInsertedNode);
    editor.focus();
    emitChange();
  };

  const toggleHighlight = () => {
    if (readOnly || !editorRef.current) {
      return;
    }

    const editor = editorRef.current;
    const range = getActiveEditorRange(editor);
    if (!range) {
      return;
    }

    if (rangeContainsHighlight(range, editor)) {
      removeHighlightInRange(range, editor);
    } else {
      highlightRange(range);
    }
    editor.focus();
    emitChange();
  };

  const handlePaste = (event: ClipboardEvent<HTMLDivElement>) => {
    if (readOnly || !editorRef.current) {
      return;
    }

    event.preventDefault();
    const plainText = event.clipboardData.getData('text/plain');
    const selection = window.getSelection();
    if (selection?.rangeCount) {
      const editor = editorRef.current;
      const range = getEditorSelectionRange(editor) ?? selection.getRangeAt(0);
      range.deleteContents();
      const textNode = document.createTextNode(plainText);
      range.insertNode(textNode);
      collapseSelectionAfterNode(textNode);
    }
    emitChange();
  };

  return {rememberSelectionRange, handleToolbarMouseDown, applyInlineFormat, clearFormatting, toggleHighlight, handlePaste};
}

export type RichTextFormatting = ReturnType<typeof useRichTextFormatting>;
