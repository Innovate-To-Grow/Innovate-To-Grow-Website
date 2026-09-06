import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {RichTextDetailEditor} from '@/features/projects/components/RichTextDetailEditor';

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

    it('pastes hostile rich clipboard content as literal plain text only', () => {
        const {editor, onChange} = renderEditor('Start ');
        const textNode = editor.firstChild;
        expect(textNode).toBeInstanceOf(Text);
        selectText(textNode as Text, 'Start '.length, 'Start '.length);

        fireEvent.paste(editor, {
            clipboardData: {
                getData: (type: string) => type === 'text/plain' ? '<img src=x onerror=alert(1)>Safe' : '<img src=x onerror=alert(1)><b>Safe</b>',
            },
        });

        expect(editor.innerHTML).toBe('Start &lt;img src=x onerror=alert(1)&gt;Safe');
        expect(editor.querySelector('img')).toBeNull();
        expect(onChange).toHaveBeenLastCalledWith('Start &lt;img src=x onerror=alert(1)&gt;Safe');
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

    it('renders read-only without a toolbar and ignores paste', () => {
        const onChange = vi.fn();
        render(<RichTextDetailEditor id="read-only" label="Note" value="<strong>fixed</strong>" readOnly onChange={onChange}/>);

        const editor = screen.getByRole('textbox', {name: 'Note'});
        expect(editor).toHaveAttribute('aria-readonly', 'true');
        expect(editor).toHaveAttribute('tabindex', '-1');
        expect(editor).toHaveAttribute('contenteditable', 'false');
        expect(screen.queryByRole('button', {name: 'Bold'})).toBeNull();
        expect(screen.queryByRole('button', {name: 'Copy All'})).toBeNull();

        fireEvent.paste(editor, {
            clipboardData: {getData: () => '<b>injected</b>'},
        });

        expect(onChange).not.toHaveBeenCalled();
    });

    it('focuses the editor when autoFocus is set', () => {
        render(<RichTextDetailEditor id="auto" label="Note" value="" autoFocus onChange={vi.fn()}/>);

        expect(screen.getByRole('textbox', {name: 'Note'})).toHaveFocus();
    });

    it('does not focus a read-only editor even with autoFocus', () => {
        render(<RichTextDetailEditor id="auto" label="Note" value="" autoFocus readOnly onChange={vi.fn()}/>);

        expect(screen.getByRole('textbox', {name: 'Note'})).not.toHaveFocus();
    });

    it('applies the large-detail-set classes', () => {
        const {container} = render(
            <RichTextDetailEditor id="large" label="Note" value="" isLargeDetailSet onChange={vi.fn()}/>,
        );

        expect(container.querySelector('.project-grid-rich-detail-editor')).toHaveClass('is-large-detail-set');
        expect(screen.getByRole('textbox', {name: 'Note'})).toHaveClass('is-large-detail-set');
    });

    it('exposes the project count as a data attribute', () => {
        const {container} = render(
            <RichTextDetailEditor id="count" label="Note" value="" projectCount={7} onChange={vi.fn()}/>,
        );

        expect(container.querySelector('.project-grid-rich-detail-editor')).toHaveAttribute('data-project-count', '7');
    });

    it('renders a header action and a copy-all button', () => {
        const onCopyAll = vi.fn();
        render(
            <RichTextDetailEditor
                id="header"
                label="Note"
                value=""
                headerAction={<span>Extra action</span>}
                onCopyAll={onCopyAll}
                onChange={vi.fn()}
            />,
        );

        expect(screen.getByText('Extra action')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', {name: 'Copy All'}));
        expect(onCopyAll).toHaveBeenCalledTimes(1);
    });

    it('emits the sanitized value when pasted with no active selection', () => {
        const {editor, onChange} = renderEditor('');
        window.getSelection()?.removeAllRanges();

        fireEvent.paste(editor, {
            clipboardData: {getData: () => 'plain'},
        });

        expect(editor.innerHTML).toBe('');
        expect(onChange).toHaveBeenCalled();
    });

    it('rewrites the DOM when the external value changes while blurred', () => {
        const {rerender} = render(
            <RichTextDetailEditor id="external" label="Note" value="<strong>one</strong>" onChange={vi.fn()}/>,
        );
        const editor = screen.getByRole('textbox', {name: 'Note'});
        expect(editor.innerHTML).toBe('<strong>one</strong>');

        rerender(<RichTextDetailEditor id="external" label="Note" value="<strong>two</strong>" onChange={vi.fn()}/>);

        expect(editor.innerHTML).toBe('<strong>two</strong>');
    });

    it('does not rewrite the DOM while the editor is focused', () => {
        const {rerender} = render(
            <RichTextDetailEditor id="focused" label="Note" value="<strong>one</strong>" onChange={vi.fn()}/>,
        );
        const editor = screen.getByRole('textbox', {name: 'Note'});
        expect(editor.innerHTML).toBe('<strong>one</strong>');

        editor.focus();
        rerender(<RichTextDetailEditor id="focused" label="Note" value="<strong>two</strong>" onChange={vi.fn()}/>);

        expect(editor.innerHTML).toBe('<strong>one</strong>');
    });

});
