interface ProjectTitleWithChipsProps {
  title: string;
  /** Added by the latest save (merged results). */
  isNew: boolean;
  /** Already in the saved results (search tables). */
  isSaved: boolean;
  savedRowLabel: string;
}

// The title keeps its own text node so it can still be found by its exact text when chips follow it.
export const ProjectTitleWithChips = ({title, isNew, isSaved, savedRowLabel}: ProjectTitleWithChipsProps) =>
  isNew || isSaved ? (
    <>
      <span>{title}</span>
      {isNew ? <span className="project-grid-row-chip is-new">New</span> : null}
      {isSaved ? <span className="project-grid-row-chip is-saved">{savedRowLabel}</span> : null}
    </>
  ) : (
    title
  );
