import './HomeDuringSemester.css';

export const HomeDuringSemester = () => {
  return (
    <div className="home-during-semester">
      <div className="home-during-hero">
        <img
          src="/i2g-header-img.jpg"
          alt="Innovate to Grow students at expo"
          className="home-during-hero-img"
        />
      </div>

      <div className="home-during-body">
        <section className="home-during-actions">
          <button className="action-button primary">EVENT REGISTRATION</button>
          <button className="action-button outlined">SUBMIT A PROJECT</button>
          <button className="action-button primary">SIGNUP FOR NEWS</button>
          <button className="action-button outlined">UPDATE MEMBERSHIP</button>
        </section>

        <section className="home-during-program">
          <h2>The Innovate to Grow program</h2>
          <p>
            Innovate to Grow (I2G) is a unique “experiential learning” program that engages external partner
            organizations with teams of students who design systems to solve real-world problems. The Innovate to
            Grow program encompasses the following experiential learning classes: <strong>Engineering Capstone</strong>,{' '}
            <strong>Engineering Service Learning</strong>, and <strong>Software Engineering Capstone</strong>.
          </p>
        </section>

        <section className="home-during-showcase">
          <div className="showcase-text">
            <h3>The Innovate to Grow showcase</h3>
            <p>
              At the end of each semester, the work completed by the student teams culminates in the Innovate to Grow
              event, a showcase of UC Merced student ingenuity and creativity, and the marquee event for the School of
              Engineering.
            </p>
            <p>Presentations will be on Campus and also streamed on Zoom.</p>
            <p className="showcase-cta">Stay tuned for the date and registration...</p>
          </div>

          <div className="showcase-video">
            <div className="video-frame">
              <iframe
                src="https://www.youtube.com/embed/oQV7O_ZFJK8"
                title="UC Merced Innovate To Grow"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
              />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

