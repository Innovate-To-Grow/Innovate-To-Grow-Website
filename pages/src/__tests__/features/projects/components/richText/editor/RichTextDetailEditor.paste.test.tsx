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
