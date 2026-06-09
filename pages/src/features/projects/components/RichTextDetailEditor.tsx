import {type ClipboardEvent, type ReactNode, useEffect, useMemo, useRef} from 'react';

import {sanitizePastProjectsDetailHtml} from './pastProjectsDetailText';
import {ClearFormattingIcon, HighlighterIcon} from './shareEditorIcons';
import {
  RICH_DETAIL_HIGHLIGHT_TAGS,
  clearInsertedFormattingAncestors,
  createPlainFormattingFragment,
  getEditorSelectionRange,
  rangeContainsHighlight,
  unwrapMatchingElements,
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
  const labelId = `${id}-label`;
  const sanitizedValue = useMemo(() => sanitizePastProjectsDetailHtml(value), [value]);
  const editorClassName = `project-grid-rich-detail-editor${isLargeDetailSet ? ' is-large-detail-set' : ''}`;
  const inputClassName = `project-grid-rich-detail-input${isLargeDetailSet ? ' is-large-detail-set' : ''}`;

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

  const applyCommand = (command: string, commandValue?: string) => {
    if (readOnly) {
      return;
    }

    editorRef.current?.focus();
    if (typeof document.execCommand === 'function') {
      // Emit semantic tags (<b>/<i>/<u>) rather than style attributes: the sanitizer's allowlist
      // has no attributes, so a `text-decoration:underline` span would be stripped and the
      // underline would silently vanish. styleWithCSS(false) keeps bold/italic/underline as tags.
      try {
        document.execCommand('styleWithCSS', false, 'false');
      } catch {
        // Older engines without styleWithCSS already default to tag output.
      }
      document.execCommand(command, false, commandValue);
    }
    emitChange();
  };

  const clearFormatting = () => {
    if (readOnly || !editorRef.current) {
      return;
    }

    const editor = editorRef.current;
    const range = getEditorSelectionRange(editor);
    if (!range) {
      return;
    }

    const selection = window.getSelection();
    const plainFragment = createPlainFormattingFragment(range.extractContents());
    const insertedNodes = Array.from(plainFragment.childNodes);
    const lastInsertedNode = insertedNodes.at(-1) ?? null;
    range.insertNode(plainFragment);
    insertedNodes.forEach((node) => clearInsertedFormattingAncestors(node, editor));

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
    const range = getEditorSelectionRange(editor);
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
    if (readOnly) {
      return;
    }

    event.preventDefault();
    const plainText = event.clipboardData.getData('text/plain');
    if (typeof document.execCommand === 'function') {
      document.execCommand('insertText', false, plainText);
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
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => applyCommand('bold')}
                >
                  <strong>B</strong>
                </button>
                <button
                  type="button"
                  className="project-grid-rich-editor-button"
                  aria-label="Italic"
                  title="Italic"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => applyCommand('italic')}
                >
                  <em>I</em>
                </button>
                <button
                  type="button"
                  className="project-grid-rich-editor-button"
                  aria-label="Underline"
                  title="Underline"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => applyCommand('underline')}
                >
                  <span style={{textDecoration: 'underline'}}>U</span>
                </button>
                <button
                  type="button"
                  className="project-grid-rich-editor-button"
                  aria-label="Highlight"
                  title="Highlight"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={toggleHighlight}
                >
                  <HighlighterIcon />
                </button>
                <button
                  type="button"
                  className="project-grid-rich-editor-button"
                  aria-label="Clear formatting"
                  title="Clear formatting"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={clearFormatting}
                >
                  <ClearFormattingIcon />
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
        onPaste={handlePaste}
        suppressContentEditableWarning
      />
    </div>
  );
}
