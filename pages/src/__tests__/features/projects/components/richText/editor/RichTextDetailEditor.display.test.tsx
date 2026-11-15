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

describe('RichTextDetailEditor', () => {
    afterEach(() => {
        cleanup();
        window.getSelection()?.removeAllRanges();
    });

    it('toggles the note editor expanded height, its button naming what a press does', () => {
        const {editor} = renderEditor('Draft note');
        const expandButton = screen.getByRole('button', {name: 'Expand note editor'});

        expect(editor).not.toHaveClass('is-expanded');
        // Not a pressed toggle as well: the name already carries the state.
        expect(expandButton).not.toHaveAttribute('aria-pressed');

        fireEvent.click(expandButton);

        expect(editor).toHaveClass('is-expanded');
        expect(screen.getByRole('button', {name: 'Collapse note editor'})).not.toHaveAttribute('aria-pressed');

        fireEvent.click(screen.getByRole('button', {name: 'Collapse note editor'}));

        expect(editor).not.toHaveClass('is-expanded');
    });

    it('says Expand on its size button and drops a dragged height when it is used', () => {
        const {editor} = renderEditor('Draft note');
        const expandButton = screen.getByRole('button', {name: 'Expand note editor'});
        expect(expandButton).toHaveTextContent('Expand');

        // The corner handle leaves the height it was dragged to on the element.
        editor.style.height = '420px';
        fireEvent.click(expandButton);

        expect(editor.style.height).toBe('');
        expect(screen.getByRole('button', {name: 'Collapse note editor'})).toHaveTextContent('Collapse');
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

});
