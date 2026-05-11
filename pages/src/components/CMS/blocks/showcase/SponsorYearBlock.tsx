import { safeHref } from '../../../../shared/utils/safeHref';

export interface SponsorYearSponsor {
  name: string;
  logo_url?: string;
  website?: string;
}

export interface SponsorYearBlockData {
  year: string;
  sponsors: SponsorYearSponsor[];
}

function normalizeSponsors(sponsors: SponsorYearSponsor[] | unknown): SponsorYearSponsor[] {
  if (!Array.isArray(sponsors)) {
    return [];
  }

  const result: SponsorYearSponsor[] = [];
  for (const sponsor of sponsors) {
    if (!sponsor || typeof sponsor !== 'object') continue;
    const candidate = sponsor as Partial<SponsorYearSponsor>;
    const name = typeof candidate.name === 'string' ? candidate.name.trim() : '';
    if (!name) continue;
    result.push({
      name,
      logo_url: typeof candidate.logo_url === 'string' ? candidate.logo_url.trim() : undefined,
      website: typeof candidate.website === 'string' ? candidate.website.trim() : undefined,
    });
  }
  return result;
}

export const SponsorYearBlock = ({ data }: { data: SponsorYearBlockData }) => {
  const year = typeof data?.year === 'string' ? data.year.trim() : '';
  const sponsors = normalizeSponsors(data?.sponsors);

  if (!year || sponsors.length === 0) {
    return null;
  }

  return (
    <section className="cms-sponsor-year">
      <h2 className="cms-sponsor-year-title">{year} Sponsors</h2>
      <div className="cms-sponsor-year-grid">
        {sponsors.map((sponsor) => {
          const content = (
            <>
              {sponsor.logo_url ? (
                <img
                  src={sponsor.logo_url}
                  alt={sponsor.name}
                  className="cms-sponsor-logo"
                  loading="lazy"
                />
              ) : (
                <div className="cms-sponsor-card-placeholder" aria-hidden="true">
                  {sponsor.name[0]?.toUpperCase() || '?'}
                </div>
              )}
              <span className="cms-sponsor-name">{sponsor.name}</span>
            </>
          );

          if (sponsor.website) {
            return (
              <a
                key={`${year}-${sponsor.name}`}
                href={safeHref(sponsor.website)}
                target="_blank"
                rel="noopener noreferrer"
                className="cms-sponsor-card"
              >
                {content}
              </a>
            );
          }

          return (
            <div key={`${year}-${sponsor.name}`} className="cms-sponsor-card">
              {content}
            </div>
          );
        })}
      </div>
    </section>
  );
};
