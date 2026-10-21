import {type ReactNode, useEffect, useMemo, useRef, useState} from 'react';

import {sanitizePastProjectsDetailHtml} from './pastProjectsDetailText';
import {RichTextToolbar} from './RichTextToolbar';
import {useRichTextFormatting} from './useRichTextFormatting';

interface RichTextDetailEditorProps {
  id: string;
  label: string;
  /** Muted text after the label, e.g. where the note is shown. Part of the field's accessible name. */
  labelHint?: string;
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
  labelHint,
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

  const formatting = useRichTextFormatting(editorRef, readOnly, emitChange);

  return (
    <div className={editorClassName} data-project-count={projectCount}>
      <div className="project-grid-rich-detail-header">
        <label id={labelId} className="project-grid-share-note-label" htmlFor={id}>
          {label}
          {labelHint ? <span className="project-grid-label-hint"> {labelHint}</span> : null}
        </label>
        {!readOnly || headerAction || onCopyAll ? (
          <div className="project-grid-rich-detail-controls">
            {onCopyAll ? (
              <button type="button" className="project-grid-rich-copy-button" onClick={onCopyAll}>
                Copy All
              </button>
            ) : null}
            {!readOnly ? (
              <RichTextToolbar
                label={label}
                formatting={formatting}
                isExpanded={isExpanded}
                onToggleExpanded={() => {
                  // A height the user dragged the box to would override the expanded/collapsed size.
                  editorRef.current?.style.removeProperty('height');
                  setIsExpanded((current) => !current);
                }}
              />
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
        onKeyUp={formatting.rememberSelectionRange}
        onMouseUp={formatting.rememberSelectionRange}
        onPaste={formatting.handlePaste}
        suppressContentEditableWarning
      />
    </div>
  );
}
