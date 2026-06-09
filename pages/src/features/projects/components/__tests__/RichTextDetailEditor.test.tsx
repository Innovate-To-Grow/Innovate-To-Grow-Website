import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {RichTextDetailEditor} from '../RichTextDetailEditor';

const renderEditor = (value: string, onChange = vi.fn()) => {
  render(<RichTextDetailEditor id="note-editor" label="Note" value={value} onChange={onChange} />);
  return {
    boldButton: screen.getByRole('button', {name: 'Bold'}),
    editor: screen.getByRole('textbox', {name: 'Note'}),
    removeFormattingButton: screen.getByRole('button', {name: 'Remove text formatting'}),
    onChange,
  };
};

const selectText = (node: Node, startOffset: number, endOffset: number) => {
  const selection = window.getSelection();
  const range = document.createRange();
  range.setStart(node, startOffset);
  range.setEnd(node, endOffset);
  selection?.removeAllRanges();
  selection?.addRange(range);
};

describe('RichTextDetailEditor', () => {
  afterEach(() => {
    cleanup();
    window.getSelection()?.removeAllRanges();
  });

  it('removes formatting from the whole note when no text is selected', () => {
    const {editor, removeFormattingButton, onChange} = renderEditor(
      '<strong>Bold</strong> and <mark>highlight</mark>',
    );
    window.getSelection()?.removeAllRanges();

    fireEvent.click(removeFormattingButton);

    expect(editor.innerHTML).toBe('Bold and highlight');
    expect(onChange).toHaveBeenLastCalledWith('Bold and highlight');
  });

  it('toggles the note editor expanded height', () => {
    const {editor} = renderEditor('Draft note');
    const expandButton = screen.getByRole('button', {name: 'Expand note editor'});

    expect(editor).not.toHaveClass('is-expanded');
    expect(expandButton).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(expandButton);

    expect(editor).toHaveClass('is-expanded');
    expect(screen.getByRole('button', {name: 'Collapse note editor'})).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', {name: 'Collapse note editor'}));

    expect(editor).not.toHaveClass('is-expanded');
  });

  it('applies bold formatting to selected text without document.execCommand', () => {
    const {boldButton, editor, onChange} = renderEditor('Bold keep');
    const textNode = editor.firstChild;
    expect(textNode).toBeInstanceOf(Text);

    selectText(textNode as Text, 0, 'Bold'.length);
    fireEvent.click(boldButton);

    expect(editor.innerHTML).toBe('<strong>Bold</strong> keep');
    expect(onChange).toHaveBeenLastCalledWith('<strong>Bold</strong> keep');
  });

  it('uses the saved editor selection when a toolbar click clears the live selection', () => {
    const {boldButton, editor, onChange} = renderEditor('Bold keep');
    const textNode = editor.firstChild;
    expect(textNode).toBeInstanceOf(Text);

    selectText(textNode as Text, 0, 'Bold'.length);
    fireEvent.mouseDown(boldButton);
    window.getSelection()?.removeAllRanges();
    fireEvent.click(boldButton);

    expect(editor.innerHTML).toBe('<strong>Bold</strong> keep');
    expect(onChange).toHaveBeenLastCalledWith('<strong>Bold</strong> keep');
  });

  it('removes formatting only from selected text inside a formatted run', () => {
    const {editor, removeFormattingButton, onChange} = renderEditor('<strong>Bold keep</strong>');
    const textNode = editor.querySelector('strong')?.firstChild;
    expect(textNode).toBeInstanceOf(Text);

    selectText(textNode as Text, 0, 'Bold'.length);
    fireEvent.click(removeFormattingButton);

    expect(editor.innerHTML).toBe('Bold<strong> keep</strong>');
    expect(onChange).toHaveBeenLastCalledWith('Bold<strong> keep</strong>');
  });
});
