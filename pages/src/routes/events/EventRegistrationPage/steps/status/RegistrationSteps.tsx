const STEPS = ['Choose event', 'Verify', 'Your details', 'Ticket'] as const;

interface RegistrationStepsProps {
  current: number;
}

/**
 * Plain, square progress row: the current step is navy on a gold rule, done
 * steps are navy outlines, later steps are grey. Signed-in visitors skip
 * "Verify" and a single open event skips "Choose event"; those steps still
 * read as done, which is what they are.
 */
export const RegistrationSteps = ({current}: RegistrationStepsProps) => (
  <ol className="event-reg-steps" aria-label="Registration steps">
    {STEPS.map((label, index) => {
      const state = index < current ? 'is-complete' : index === current ? 'is-current' : 'is-upcoming';
      return (
        <li key={label} className={`event-reg-step ${state}`} aria-current={index === current ? 'step' : undefined}>
          <span className="event-reg-step-number" aria-hidden="true">
            {index + 1}
          </span>
          <span className="event-reg-step-label">{label}</span>
          {index < current ? <span className="sr-only"> (done)</span> : null}
        </li>
      );
    })}
  </ol>
);
