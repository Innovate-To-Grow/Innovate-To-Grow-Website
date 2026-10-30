import type {ReactNode} from 'react';
import type {SignInToSave} from './curationNote';

interface SignInToSaveLinkProps {
  signIn: SignInToSave;
  className?: string;
  /** The link's text on the site itself ("Sign in to save"). */
  children: ReactNode;
}

/**
 * The draft's sign-in link. In the widget, signing in inside the partner's frame would neither reach the site's
 * own tabs nor keep the draft, so it continues on the full Past Projects page in a new tab, draft included.
 */
export const SignInToSaveLink = ({signIn, className, children}: SignInToSaveLinkProps) =>
  signIn.inNewTab ? (
    <a className={className} href={signIn.href} target="_blank" rel="noopener">
      Continue in Past Projects
      {/* The space is inside the hidden text, so the link's underline stops at its last visible word. */}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  ) : (
    <a className={className} href={signIn.href}>
      {children}
    </a>
  );
