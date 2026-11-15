import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {RichTextDetailEditor} from '@/features/projects/components/richText/editor/RichTextDetailEditor';

const renderEditor = (value: string, onChange = vi.fn()) => {
    render(<RichTextDetailEditor id="note-editor" label="Note" value={value} onChange={onChange}/>);
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

    it('groups the formatting buttons under a name screen readers announce', () => {
        renderEditor('Draft note');

        const toolbar = screen.getByRole('group', {name: 'Note formatting'});
        expect(toolbar).toContainElement(screen.getByRole('button', {name: 'Bold'}));
        expect(toolbar).toContainElement(screen.getByRole('button', {name: 'Expand note editor'}));
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

    it('applies italic formatting to selected text', () => {
        const {editor, onChange} = renderEditor('Italic keep');
        const textNode = editor.firstChild;
        expect(textNode).toBeInstanceOf(Text);

        selectText(textNode as Text, 0, 'Italic'.length);
        fireEvent.click(screen.getByRole('button', {name: 'Italic'}));

        expect(editor.innerHTML).toBe('<em>Italic</em> keep');
        expect(onChange).toHaveBeenLastCalledWith('<em>Italic</em> keep');
    });

    it('applies underline formatting to selected text', () => {
        const {editor, onChange} = renderEditor('Underline keep');
        const textNode = editor.firstChild;
        expect(textNode).toBeInstanceOf(Text);

        selectText(textNode as Text, 0, 'Underline'.length);
        fireEvent.click(screen.getByRole('button', {name: 'Underline'}));

        expect(editor.innerHTML).toBe('<u>Underline</u> keep');
        expect(onChange).toHaveBeenLastCalledWith('<u>Underline</u> keep');
    });

    it('removes bold from already-bold selected text', () => {
        const {editor, onChange} = renderEditor('<strong>Bold</strong> keep');
        const textNode = editor.querySelector('strong')?.firstChild;
        expect(textNode).toBeInstanceOf(Text);

        selectText(textNode as Text, 0, 'Bold'.length);
        fireEvent.click(screen.getByRole('button', {name: 'Bold'}));

        expect(editor.innerHTML).toBe('Bold keep');
        expect(onChange).toHaveBeenLastCalledWith('Bold keep');
    });

    it('highlights selected text with a mark element', () => {
        const {editor, onChange} = renderEditor('Highlight keep');
        const textNode = editor.firstChild;
        expect(textNode).toBeInstanceOf(Text);

        selectText(textNode as Text, 0, 'Highlight'.length);
        fireEvent.click(screen.getByRole('button', {name: 'Highlight'}));

        expect(editor.innerHTML).toBe('<mark>Highlight</mark> keep');
        expect(onChange).toHaveBeenLastCalledWith('<mark>Highlight</mark> keep');
    });

    it('toggles a highlight off on the second click', () => {
        const {editor, onChange} = renderEditor('Highlight keep');
        const textNode = editor.firstChild;
        expect(textNode).toBeInstanceOf(Text);

        selectText(textNode as Text, 0, 'Highlight'.length);
        const highlightButton = screen.getByRole('button', {name: 'Highlight'});
        fireEvent.click(highlightButton);
        expect(editor.innerHTML).toBe('<mark>Highlight</mark> keep');

        // Re-select the highlighted text and toggle it back off.
        const markText = editor.querySelector('mark')?.firstChild;
        expect(markText).toBeInstanceOf(Text);
        selectText(markText as Text, 0, 'Highlight'.length);
        fireEvent.mouseDown(highlightButton);
        fireEvent.click(highlightButton);

        expect(editor.innerHTML).toBe('Highlight keep');
        expect(onChange).toHaveBeenLastCalledWith('Highlight keep');
    });

});
