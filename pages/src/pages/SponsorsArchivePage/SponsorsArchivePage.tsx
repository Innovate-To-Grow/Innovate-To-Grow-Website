import {useParams} from 'react-router-dom';
import './SponsorsArchivePage.css';

const SPONSORS_DATA: Record<string, {title: string; description?: string; image: string}> = {
  '2014': {
    title: '2014 Sponsors',
    image: '/media/sponsors/140424_innovatetogrow_sponsors.jpg',
  },
  '2015': {
    title: '2015 Sponsors',
    description:
      'UC Merced is honored to acknowledge sponsors for commitment to and partnership with our programs. Recognition includes acknowledgement in all publicity materials, fliers and posters, all email announcements and in media releases and publications of the Innovate to Grow competition.',
    image: '/media/sponsors/140424_innovatetogrow_sponsors_web.jpg',
  },
};

export const SponsorsArchivePage = () => {
  const {year} = useParams<{year: string}>();
  const data = year ? SPONSORS_DATA[year] : undefined;

  if (!data) {
    return (
      <div className="sponsors-archive-page">
        <h1 className="sponsors-archive-page-title">Sponsors Archive</h1>
        <p className="sponsors-archive-text">The requested sponsors page was not found.</p>
      </div>
    );
  }

  return (
    <div className="sponsors-archive-page">
      <h1 className="sponsors-archive-page-title">{data.title}</h1>
      {data.description && <p className="sponsors-archive-text">{data.description}</p>}
      <img
        className="sponsors-archive-image"
        src={data.image}
        alt={data.title}
        width={800}
        height={600}
        loading="lazy"
      />
    </div>
  );
};
