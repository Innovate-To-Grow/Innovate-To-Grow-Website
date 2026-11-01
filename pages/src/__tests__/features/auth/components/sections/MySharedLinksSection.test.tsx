import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MySharedLinksSection} from '@/features/auth/components/sections/MySharedLinksSection';

const mockListMyShares = vi.fn();
const mockDeleteShare = vi.fn();

vi.mock('@/features/projects/api', () => ({
    DEFAULT_PAST_PROJECT_SHARE_NAME: 'Past Project Curation',
    listMyShares: () => mockListMyShares(),
    deleteShare: (id: string) => mockDeleteShare(id),
}));

const share = (overrides = {}) => ({
    id: 'share-1',
    name: 'Spring finalists',
    note: '',
    version: 1,
    share_url: 'https://example.test/past-projects/share-1',
    row_count: 3,
    created_at: '2026-06-05T00:00:00Z',
    ...overrides,
});

describe('MySharedLinksSection', () => {
    beforeEach(() => {
        mockListMyShares.mockReset();
        mockDeleteShare.mockReset();
    });

    afterEach(() => {
        cleanup();
        vi.unstubAllGlobals();
        Object.defineProperty(document, 'execCommand', {configurable: true, writable: true, value: undefined});
    });

    it('copies a share link and announces it in the success colour', async () => {
        const writeText = vi.fn().mockResolvedValue(undefined);
        vi.stubGlobal('navigator', {...window.navigator, clipboard: {writeText}});
        mockListMyShares.mockResolvedValue([share()]);
        render(<MySharedLinksSection/>);

        fireEvent.click(await screen.findByRole('button', {name: /^Copy Link to Spring finalists/}));

        await waitFor(() => expect(writeText).toHaveBeenCalledWith('https://example.test/past-projects/share-1'));
        expect(await screen.findByRole('status')).toHaveTextContent(/^Link copied\.$/);
        const message = screen.getByText('Link copied.');
        expect(message).toHaveClass('itg-success');
        expect(message).not.toHaveClass('itg-error');
        // The message is the only child of its element, for page translation.
        expect(message.childNodes).toHaveLength(1);
        expect(message.firstChild?.nodeType).toBe(Node.TEXT_NODE);
    });

    it('reports a copy the browser refuses in the error colour', async () => {
        const writeText = vi.fn().mockRejectedValue(new Error('denied'));
        vi.stubGlobal('navigator', {...window.navigator, clipboard: {writeText}});
        Object.defineProperty(document, 'execCommand', {configurable: true, writable: true, value: () => false});
        mockListMyShares.mockResolvedValue([share()]);
        render(<MySharedLinksSection/>);

        fireEvent.click(await screen.findByRole('button', {name: /^Copy Link to Spring finalists/}));

        const failed = 'Could not copy the link. Open it and copy the address instead.';
        expect(await screen.findByRole('status')).toHaveTextContent(failed);
        expect(screen.getByText(failed)).toHaveClass('itg-error');
        expect(screen.getByText(failed)).not.toHaveClass('itg-success');
    });

    it('keeps the copy status line empty until a copy', async () => {
        mockListMyShares.mockResolvedValue([share()]);
        render(<MySharedLinksSection/>);

        await screen.findByText('Spring finalists');
        // Empty, so .account-shares-copy-status:empty hides it.
        expect(screen.getByRole('status')).toBeEmptyDOMElement();
    });

    it('renders the list with copy, open and delete when the user has shares', async () => {
        mockListMyShares.mockResolvedValue([share()]);
        render(<MySharedLinksSection/>);

        expect(await screen.findByRole('heading', {
            level: 2,
            name: 'Past Project Curation Shared Links'
        })).toBeInTheDocument();
        expect(await screen.findByText('Spring finalists')).toBeInTheDocument();
        const openLink = screen.getByRole('link', {name: /open/i});
        expect(openLink).toHaveAttribute('href', '/past-projects/share-1');
        expect(openLink).toHaveClass('account-outline-btn');
        expect(screen.getByRole('link', {name: /view full page/i})).toHaveAttribute(
            'href',
            '/account/past-project-curation-shared-links',
        );
        // Its name starts with the visible "Copy Link" (Title Case, like every control label), so speech input can press
        // it by what it says.
        expect(screen.getByRole('button', {name: /^Copy Link to Spring finalists/})).toHaveTextContent(/^Copy Link$/);
        expect(screen.getByRole('link', {name: /^Open Spring finalists/})).toHaveTextContent(/^Open$/);
        expect(screen.getByRole('button', {name: /^Delete Spring finalists/})).toHaveTextContent(/^Delete$/);
        expect(screen.getByRole('button', {name: /delete/i})).toBeInTheDocument();
    });

    it('shows the default curation title for a share stored without a name', async () => {
        mockListMyShares.mockResolvedValue([share({name: ''})]);
        render(<MySharedLinksSection/>);

        expect(await screen.findByText('Past Project Curation')).toBeInTheDocument();
        // Several unnamed shares look alike, so each control names the row it acts on.
        expect(screen.getByRole('link', {name: /^Open Past Project Curation \(3 results · /})).toBeInTheDocument();
        expect(screen.getByRole('button', {name: /^Delete Past Project Curation \(3 results · /})).toBeInTheDocument();
    });

    it('dates each share by its last change when the server sends one', async () => {
        mockListMyShares.mockResolvedValue([
            share({id: 'edited', name: 'Edited list', updated_at: '2026-10-18T12:00:00Z'}),
            share({id: 'legacy', name: 'Legacy list'}),
        ]);
        render(<MySharedLinksSection/>);

        const edited = new Date('2026-10-18T12:00:00Z').toLocaleDateString();
        const created = new Date('2026-06-05T00:00:00Z').toLocaleDateString();
        expect(await screen.findByText(`3 results · ${edited}`)).toBeInTheDocument();
        expect(screen.getByText(`3 results · ${created}`)).toBeInTheDocument();
    });

    it('deletes a share after confirmation and removes it from the list', async () => {
        mockListMyShares.mockResolvedValue([share()]);
        mockDeleteShare.mockResolvedValue(undefined);
        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

        render(<MySharedLinksSection/>);
        await screen.findByText('Spring finalists');

        fireEvent.click(screen.getByRole('button', {name: /delete/i}));

        await waitFor(() => expect(mockDeleteShare).toHaveBeenCalledWith('share-1'));
        await waitFor(() => expect(screen.queryByText('Spring finalists')).toBeNull());
        confirmSpy.mockRestore();
    });

    it('keeps the compact section visible and surfaces a failed deletion', async () => {
        mockListMyShares.mockResolvedValue([share()]);
        mockDeleteShare.mockRejectedValue({response: {status: 503, data: {detail: 'Try again later'}}});
        vi.spyOn(window, 'confirm').mockReturnValue(true);

        render(<MySharedLinksSection/>);
        await screen.findByText('Spring finalists');
        fireEvent.click(screen.getByRole('button', {name: /delete/i}));

        expect(await screen.findByText('Try again later')).toBeInTheDocument();
        expect(screen.getByText('Spring finalists')).toBeInTheDocument();
        expect(screen.getByRole('heading', {name: 'Past Project Curation Shared Links'})).toBeInTheDocument();
    });

    it('renders nothing when the user has no shares', async () => {
        mockListMyShares.mockResolvedValue([]);
        const {container} = render(<MySharedLinksSection/>);

        await waitFor(() => expect(container).toBeEmptyDOMElement());
    });

});
