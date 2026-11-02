/**
 * Props for a button its own press can leave with nothing to do (Deselect, Undo, Remove Selected…). The native
 * `disabled` would throw keyboard focus out of the button that was just pressed, to the page, so it is marked
 * with aria-disabled instead: it keeps focus and its place in the tab order, says it is unavailable, and ignores
 * presses. The global button styles grey out both kinds alike.
 */
export const softDisabled = (disabled: boolean, onClick: () => void) => ({
  'aria-disabled': disabled || undefined,
  onClick: disabled ? undefined : onClick,
});
