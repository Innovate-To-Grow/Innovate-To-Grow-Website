import {ClearFormattingIcon, CollapseEditorIcon, ExpandEditorIcon, HighlighterIcon} from './shareEditorIcons';
import type {RichTextFormatting} from './useRichTextFormatting';

interface RichTextToolbarProps {
  label: string;
  formatting: RichTextFormatting;
  isExpanded: boolean;
  onToggleExpanded: () => void;
}

/**
 * Bold / italic / underline / highlight / clear formatting, and the expand-collapse toggle. A named group (a
 * toolbar role would promise arrow-key navigation between the buttons).
 */
export const RichTextToolbar = ({label, formatting, isExpanded, onToggleExpanded}: RichTextToolbarProps) => (
  <div className="project-grid-rich-detail-toolbar" role="group" aria-label={`${label} formatting`}>
    <button
      type="button"
      className="project-grid-rich-editor-button"
      aria-label="Bold"
      title="Bold"
      onMouseDown={formatting.handleToolbarMouseDown}
      onClick={() => formatting.applyInlineFormat('bold', 'strong')}
    >
      <strong>B</strong>
    </button>
    <button
      type="button"
      className="project-grid-rich-editor-button"
      aria-label="Italic"
      title="Italic"
      onMouseDown={formatting.handleToolbarMouseDown}
      onClick={() => formatting.applyInlineFormat('italic', 'em')}
    >
      <em>I</em>
    </button>
    <button
      type="button"
      className="project-grid-rich-editor-button"
      aria-label="Underline"
      title="Underline"
      onMouseDown={formatting.handleToolbarMouseDown}
      onClick={() => formatting.applyInlineFormat('underline', 'u')}
    >
      <span className="project-grid-rich-editor-underline">U</span>
    </button>
    <button
      type="button"
      className="project-grid-rich-editor-button"
      aria-label="Highlight"
      title="Highlight"
      onMouseDown={formatting.handleToolbarMouseDown}
      onClick={formatting.toggleHighlight}
    >
      <HighlighterIcon />
    </button>
    <button
      type="button"
      className="project-grid-rich-editor-button"
      aria-label="Remove text formatting"
      title="Remove text formatting"
      onMouseDown={formatting.handleToolbarMouseDown}
      onClick={formatting.clearFormatting}
    >
      <ClearFormattingIcon />
    </button>
    {/* Its name says what a press does, as its visible word does, so it is not also a pressed toggle (which read
        "Collapse note editor, pressed"). */}
    <button
      type="button"
      className={`project-grid-rich-editor-button project-grid-rich-editor-size-button${isExpanded ? ' is-active' : ''}`}
      aria-label={isExpanded ? 'Collapse note editor' : 'Expand note editor'}
      title={isExpanded ? 'Collapse note editor' : 'Expand note editor'}
      onMouseDown={(event) => event.preventDefault()}
      onClick={onToggleExpanded}
    >
      {isExpanded ? <CollapseEditorIcon /> : <ExpandEditorIcon />}
      <span aria-hidden="true">{isExpanded ? 'Collapse' : 'Expand'}</span>
    </button>
  </div>
);
