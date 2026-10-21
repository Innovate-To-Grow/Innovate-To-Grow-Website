import {useEffect, type ReactNode} from 'react';
import {Link, useLocation, useParams} from 'react-router';
import {ProjectsMessagePage} from '@/features/projects/components/ProjectsMessagePage';
import {formatTermForProse, splitStudentNames} from '@/features/projects/components/projectGrid';
import {useCopyLink} from '@/hooks/useCopyLink';
import {useProjectDetail} from '@/features/projects/hooks/useProjectDetail';
import {formatSemesterLabel} from '@/lib/format';
import {usePageTitle} from '@/hooks/usePageTitle';
import './ProjectDetailPage.css';

type ProjectDetail = NonNullable<ReturnType<typeof useProjectDetail>['result']>;

interface ProjectLoadFailedProps {
  error: string | null;
  backLink: ReactNode;
  retry: () => void;
}

/** A project that does not exist (or a link that is wrong), or one that could not be loaded right now. */
const ProjectLoadFailed = ({error, backLink, retry}: ProjectLoadFailedProps) => {
  const notFound = error !== 'failed';
  return (
    <ProjectsMessagePage
      className="project-detail projects-error"
      before={backLink}
      title={notFound ? "We couldn't find this project" : "We couldn't load this project"}
      actions={
        <>
          {notFound ? null : (
            <button type="button" className="itg-btn itg-btn-primary" onClick={retry}>
              Try again
            </button>
          )}
          <Link className={`itg-btn ${notFound ? 'itg-btn-primary' : 'itg-btn-outline'}`} to="/past-projects">
            Search past projects
          </Link>
          <Link className="itg-link" to="/current-projects">
            Current Projects
          </Link>
        </>
      }
    >
      <p>
        {notFound
          ? 'The link may be incomplete, or the project has been removed from the catalog. Search for it by title, team or organization.'
          : 'Unable to load this project. Check your connection and try again, or search for it by title, team or organization.'}
      </p>
    </ProjectsMessagePage>
  );
};

/** The labelled facts shown in the meta box (empty ones are left out). */
const projectFacts = ({project, classLabel}: ProjectDetail, term: string): Array<[string, string]> => [
  ['Term', term],
  ['Class', classLabel && project.class_code ? `${classLabel} (${project.class_code})` : project.class_code],
  ['Team #', project.team_number],
  ['Team', project.team_name],
  ['Organization', project.organization],
  ['Industry', project.industry],
];

/** The project's header, facts, abstract and team members. */
const ProjectDetailBody = ({result}: {result: ProjectDetail}) => {
  const {project, classLabel} = result;
  const term = formatSemesterLabel(project.semester_label || '');
  // Current projects name their class from the schedule ("Engineering Capstone"); archive projects have the code only.
  const eyebrow = [classLabel || project.class_code, formatTermForProse(term)].filter(Boolean).join(' · ');
  const byline = [project.team_name, project.organization].filter(Boolean).join(' · ');
  const members = splitStudentNames(project.student_names);
  const facts = projectFacts(result, term);
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

interface ProjectDetailActionsProps {
  backHref: string;
  backLabel: string;
}

/** Back to the list, and copy a link to this project. */
const ProjectDetailActions = ({backHref, backLabel}: ProjectDetailActionsProps) => {
  const {status: copyStatus, copy} = useCopyLink({
    copied: 'Link copied.',
    failed: 'Could not copy the link. Copy it from the address bar instead.',
  });
  return (
    <div className="project-detail-actions">
      <Link to={backHref} className="itg-link project-detail-actions-back">
        <span className="project-detail-wide-only" aria-hidden="true">
          ‹{' '}
        </span>
        {backLabel}
      </Link>
      <button
        type="button"
        className="itg-btn itg-btn-text project-detail-copy"
        onClick={() => void copy(window.location.href)}
      >
        <span>
          Copy link <span className="project-detail-wide-only">to this project</span>
        </span>
      </button>
      {copyStatus ? (
        <p className="project-detail-copy-status" role="status">
          {copyStatus}
        </p>
      ) : null}
    </div>
  );
};

export const ProjectDetailPage = () => {
  const {id} = useParams<{id: string}>();
  const location = useLocation();
  const isPastProjectDetail = location.pathname.startsWith('/past-projects/project/');
  const backHref = isPastProjectDetail ? '/past-projects' : '/current-projects';
  const backLabel = isPastProjectDetail ? 'Back to Past Projects' : 'Back to Current Projects';
  // /projects/:id is linked from Current Projects and Presenting Teams by this semester's schedule ids, and by
  // older links to archive projects: it looks in the current schedule first. Past-project pages read the archive.
  const {result, loading, error, retry} = useProjectDetail(id, !isPastProjectDetail);
  usePageTitle(result?.project.project_title || (isPastProjectDetail ? 'Past Projects' : 'Current Projects'));

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [id]);

  const backLink = (
    <Link to={backHref} className="itg-back-link project-detail-back">
      <span>
        <span aria-hidden="true">‹ </span>
        {backLabel}
      </span>
    </Link>
  );

  if (loading) {
    return (
      <div className="project-detail">
        <p className="itg-loading">Loading...</p>
      </div>
    );
  }

  if (error || !result) {
    return <ProjectLoadFailed error={error} backLink={backLink} retry={retry} />;
  }

  return (
    <article className="project-detail">
      {backLink}
      <ProjectDetailBody result={result} />
      <ProjectDetailActions backHref={backHref} backLabel={backLabel} />
    </article>
  );
};
