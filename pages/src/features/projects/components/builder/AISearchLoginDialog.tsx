import {buildLoginPath} from '@/features/auth/api/redirects';
import {PastProjectsDialog} from './PastProjectsDialog';

/** Shown when a visitor who is not signed in asks for an AI search table. */
export const AISearchLoginDialog = ({onClose}: {onClose: () => void}) => (
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
