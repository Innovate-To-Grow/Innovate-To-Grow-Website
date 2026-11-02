import {
  formatTermForProse,
  getDefaultClassName,
  getDisplayTeamNumber,
  splitStudentNames,
} from '@/features/projects/components/grid/contracts/projectGrid';
import type {ProjectPresentation, ResolvedProjectDetail} from '@/features/projects/hooks/useProjectDetail';
import {formatSemesterLabel} from '@/lib/format';

/** "Track 2 · 1:30 · Glacier 165" for a presenting team (whatever the schedule gives), "Not presenting" otherwise. */
const showcaseText = (presentation: ProjectPresentation | null | undefined) =>
  presentation
    ? [presentation.track, presentation.time, presentation.room].filter(Boolean).join(' · ') || 'Presenting'
    : 'Not presenting';

/**
 * The labelled facts shown in the meta box (empty ones are left out). The term reads as the eyebrow writes it
 * ("Spring 2026"), and a current project says whether, and where, the team presents at the showcase.
 */
const projectFacts = (
  {project, source, presentation}: ResolvedProjectDetail,
  className: string,
  term: string,
): Array<[string, string]> => [
  ['Term', term],
  ['Class', className && project.class_code ? `${className} (${project.class_code})` : project.class_code],
  ['Team #', getDisplayTeamNumber(project)],
  ['Team', project.team_name],
  ['Organization', project.organization],
  ['Industry', project.industry],
  ['Showcase', source === 'current' ? showcaseText(presentation) : ''],
];

/** The project's header, facts, abstract and team members. */
export const ProjectDetailBody = ({result}: {result: ResolvedProjectDetail}) => {
  const {project, classLabel} = result;
  const term = formatTermForProse(formatSemesterLabel(project.semester_label || ''));
  // The schedule names current classes ("Engineering Capstone"); archive projects carry the code, named the same way.
  const className = classLabel || getDefaultClassName(project.class_code);
  const eyebrow = [className || project.class_code, term].filter(Boolean).join(' · ');
  const byline = [project.team_name, project.organization].filter(Boolean).join(' · ');
  const members = splitStudentNames(project.student_names);
  const facts = projectFacts(result, className, term);
  return (
    <>
      <header className="project-detail-header">
        {eyebrow ? <p className="itg-eyebrow">{eyebrow}</p> : null}
        <h1 className="itg-page-title project-detail-title">{project.project_title}</h1>
        {byline ? <p className="itg-page-meta project-detail-byline">{byline}</p> : null}
      </header>

      <dl className="itg-meta-box project-detail-meta">
        {facts
          .filter(([, value]) => Boolean(value))
          .map(([label, value]) => (
            <div key={label} className="itg-meta-item">
              <dt className="itg-meta-label">{label}</dt>
              <dd className="itg-meta-value">{value}</dd>
            </div>
          ))}
      </dl>

      {project.abstract ? (
        <section className="project-detail-section" aria-labelledby="project-detail-abstract-title">
          <h2 id="project-detail-abstract-title" className="itg-section-title">
            Abstract
          </h2>
          <p className="project-detail-abstract">{project.abstract}</p>
        </section>
      ) : null}

      {members.length ? (
        <section className="project-detail-section" aria-labelledby="project-detail-members-title">
          <h2 id="project-detail-members-title" className="itg-section-title">
            Team members
          </h2>
          <ul className="project-detail-members">
            {members.map((name, index) => (
              <li key={`${name}-${index}`}>{name}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
};
