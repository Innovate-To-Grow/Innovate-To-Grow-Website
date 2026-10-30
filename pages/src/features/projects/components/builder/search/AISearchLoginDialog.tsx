import {buildLoginPath} from '@/features/auth/api/redirects';
import type {ProjectGridRow} from '../../grid/contracts/projectGrid';
import {PastProjectsDialog} from '../dialog/PastProjectsDialog';
import {draftHandoverHref, isEmbeddedBuilder} from '../draft/draftHandover';

interface AISearchLoginDialogProps {
  /** The builder's draft, carried to the full page when the dialog is shown in the widget. */
  draftRows?: readonly ProjectGridRow[];
  onClose: () => void;
}

/**
 * Shown when a visitor who is not signed in asks for an AI search table. In the widget, signing in inside the
 * partner's frame loaded the whole site (header, menu, footer) into it, so there the visitor continues on the
 * full Past Projects page in a new tab, with the draft (draftHandover.ts).
 */
export const AISearchLoginDialog = ({draftRows = [], onClose}: AISearchLoginDialogProps) =>
  isEmbeddedBuilder() ? (
    <PastProjectsDialog
      title="Sign in required"
      cancelLabel="Close"
      confirmLabel="Continue in Past Projects"
      confirmHref={draftHandoverHref(draftRows)}
      onCancel={onClose}
      // Closed after the click: a link taken off the page while its click is handled opens nothing.
      onConfirm={() => window.setTimeout(onClose)}
    >
      <p>
        AI search needs you to sign in on the Innovate to Grow site. Past Projects opens in a new tab, with your
        curation draft, where you can sign in and use it.
      </p>
    </PastProjectsDialog>
  ) : (
    <PastProjectsDialog
      title="Sign in required"
      cancelLabel="Close"
      confirmLabel="Sign In"
      onCancel={onClose}
      onConfirm={() => {
        window.location.href = buildLoginPath(`${window.location.pathname}${window.location.search}`);
      }}
    >
      <p>You need to sign in before using AI search.</p>
    </PastProjectsDialog>
  );
