import {type ClipboardEvent, type MouseEvent, type ReactNode, useEffect, useMemo, useRef, useState} from 'react';

import {sanitizePastProjectsDetailHtml} from './pastProjectsDetailText';
import {ClearFormattingIcon, CollapseEditorIcon, ExpandEditorIcon, HighlighterIcon} from './shareEditorIcons';
import {
  RICH_DETAIL_HIGHLIGHT_TAGS,
  RICH_DETAIL_INLINE_FORMAT_TAGS,
  clearInsertedFormattingAncestors,
  getEditorSelectionRange,
  rangeContainsFormatting,
  rangeContainsHighlight,
  replaceRangeWithoutMatchingFormatting,
  replaceEditorWithPlainFormatting,
  replaceRangeWithPlainFormatting,
  unwrapMatchingElements,
  wrapRangeWithFormatting,
} from './richTextEditorDom';

interface RichTextDetailEditorProps {
  id: string;
  label: string;
  value: string;
  placeholder?: string;
  readOnly?: boolean;
  autoFocus?: boolean;
  isLargeDetailSet?: boolean;
  projectCount?: number;
  headerAction?: ReactNode;
  onCopyAll?: () => void;
  onChange: (value: string) => void;
}

/**
 * A contentEditable rich-text editor supporting bold / italic / highlight / clear-formatting,
 * used for per-project curation notes. Sanitizes on every emit and on external value changes.
 */
export function RichTextDetailEditor({
  id,
  label,
  value,
  placeholder = '',
  readOnly = false,
  autoFocus = false,
  isLargeDetailSet = false,
  projectCount,
  headerAction,
  onCopyAll,
  onChange,
}: RichTextDetailEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null);
  const lastSelectionRangeRef = useRef<Range | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const labelId = `${id}-label`;
  const sanitizedValue = useMemo(() => sanitizePastProjectsDetailHtml(value), [value]);
  const editorClassName = `project-grid-rich-detail-editor${isLargeDetailSet ? ' is-large-detail-set' : ''}`;
  const inputClassName = [
    'project-grid-rich-detail-input',
    isLargeDetailSet ? 'is-large-detail-set' : '',
    isExpanded ? 'is-expanded' : '',
  ]
    .filter(Boolean)
    .join(' ');

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) {
      return;
    }
    // Don't rewrite innerHTML while the user is actively editing this field: the DOM already holds
    // their input and a rewrite would reset the caret/selection mid-edit (the browser's live
    // markup often differs from DOMPurify's normalized output). The focus guard — rather than the
    // earlier value-echo guard, which went stale and could leave the DOM showing a removed row —
    // only applies external value changes (prop/share reseed, programmatic seeding) when the
    // editor is not focused, which is exactly when those happen.
    if (editor.innerHTML === sanitizedValue || document.activeElement === editor) {
      return;
    }
    editor.innerHTML = sanitizedValue;
  }, [sanitizedValue]);

  useEffect(() => {
    if (autoFocus && !readOnly) {
      editorRef.current?.focus();
    }
  }, [autoFocus, readOnly]);

  const emitChange = () => {
    const nextValue = sanitizePastProjectsDetailHtml(editorRef.current?.innerHTML ?? '');
    onChange(nextValue);
  };

  const rangeBelongsToEditor = (range: Range, editor: HTMLElement) => {
    const ownsNode = (node: Node) => node === editor || editor.contains(node);
    return ownsNode(range.startContainer) && ownsNode(range.endContainer);
  };

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
    if (!firstNode || !lastNode) {
      return;
    }

    const selection = window.getSelection();
    if (!selection) {
      return;
    }

    const nextRange = document.createRange();
    nextRange.setStartBefore(firstNode);
    nextRange.setEndAfter(lastNode);
    selection.removeAllRanges();
    selection.addRange(nextRange);
    lastSelectionRangeRef.current = nextRange.cloneRange();
  };

  const collapseSelectionAfterNode = (node: Node | null) => {
    const selection = window.getSelection();
    if (!node || !selection) {
      return;
    }

    const nextRange = document.createRange();
    nextRange.setStartAfter(node);
    nextRange.collapse(true);
    selection.removeAllRanges();
    selection.addRange(nextRange);
    lastSelectionRangeRef.current = null;
  };

  const handleToolbarMouseDown = (event: MouseEvent<HTMLButtonElement>) => {
    rememberSelectionRange();
    event.preventDefault();
  };

  const applyInlineFormat = (format: keyof typeof RICH_DETAIL_INLINE_FORMAT_TAGS, tagName: string) => {
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

  const removeHighlight = (range: Range, editor: HTMLElement) => {
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
      selection.removeAllRanges();
      selection.addRange(nextRange);
    }

    editor.focus();
    emitChange();
  };

  const applyHighlight = (range: Range, editor: HTMLElement) => {
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
      selection.removeAllRanges();
      selection.addRange(nextRange);
    }

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
      removeHighlight(range, editor);
      return;
    }

    applyHighlight(range, editor);
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

  return (
    <div className={editorClassName} data-project-count={projectCount}>
      <div className="project-grid-rich-detail-header">
        <label id={labelId} className="project-grid-share-note-label" htmlFor={id}>
          {label}
        </label>
        {!readOnly || headerAction || onCopyAll ? (
          <div className="project-grid-rich-detail-controls">
            {onCopyAll ? (
              <button type="button" className="project-grid-rich-copy-button" onClick={onCopyAll}>
                Copy All
              </button>
            ) : null}
            {!readOnly ? (
              <div className="project-grid-rich-detail-toolbar" aria-label={`${label} formatting`}>
                <button
                  type="button"
                  className="project-grid-rich-editor-button"
                  aria-label="Bold"
                  title="Bold"
                  onMouseDown={handleToolbarMouseDown}
                  onClick={() => applyInlineFormat('bold', 'strong')}
                >
                  <strong>B</strong>
                </button>
                <button
                  type="button"
                  className="project-grid-rich-editor-button"
                  aria-label="Italic"
                  title="Italic"
                  onMouseDown={handleToolbarMouseDown}
                  onClick={() => applyInlineFormat('italic', 'em')}
                >
                  <em>I</em>
                </button>
                <button
                  type="button"
                  className="project-grid-rich-editor-button"
                  aria-label="Underline"
                  title="Underline"
                  onMouseDown={handleToolbarMouseDown}
                  onClick={() => applyInlineFormat('underline', 'u')}
                >
                  <span style={{textDecoration: 'underline'}}>U</span>
                </button>
                <button
                  type="button"
                  className="project-grid-rich-editor-button"
                  aria-label="Highlight"
                  title="Highlight"
                  onMouseDown={handleToolbarMouseDown}
                  onClick={toggleHighlight}
                >
                  <HighlighterIcon />
                </button>
                <button
                  type="button"
                  className="project-grid-rich-editor-button"
                  aria-label="Remove text formatting"
                  title="Remove text formatting"
                  onMouseDown={handleToolbarMouseDown}
                  onClick={clearFormatting}
                >
                  <ClearFormattingIcon />
                </button>
                <button
                  type="button"
                  className="project-grid-rich-editor-button"
                  aria-label={isExpanded ? 'Collapse note editor' : 'Expand note editor'}
                  aria-pressed={isExpanded}
                  title={isExpanded ? 'Collapse note editor' : 'Expand note editor'}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => setIsExpanded((current) => !current)}
                >
                  {isExpanded ? <CollapseEditorIcon /> : <ExpandEditorIcon />}
                </button>
              </div>
            ) : null}
            {headerAction}
          </div>
        ) : null}
      </div>
      <div
        ref={editorRef}
        id={id}
        className={inputClassName}
        role="textbox"
        aria-labelledby={labelId}
        aria-multiline="true"
        aria-readonly={readOnly}
        contentEditable={!readOnly}
        data-placeholder={placeholder}
        spellCheck
        tabIndex={readOnly ? -1 : 0}
        onInput={emitChange}
        onBlur={emitChange}
        onKeyUp={rememberSelectionRange}
        onMouseUp={rememberSelectionRange}
        onPaste={handlePaste}
        suppressContentEditableWarning
      />
    </div>
  );
}
