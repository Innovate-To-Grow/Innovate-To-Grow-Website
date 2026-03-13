import './JudgingPage.css';

export const JudgingPage = () => {
  return (
    <div className="judging-page">
      <h1 className="judging-page-title">Judging Forms</h1>

      <section className="judging-page-section">
        <p className="judging-page-text">
          The judging form is available in the respective track:
        </p>
        <ul className="judging-page-list">
          <li>Via QR code in the Room.</li>
          <li>Via URL in the chat of the Zoom Room.</li>
          <li>
            The judge form depends on the class (e.g. Engineering versus Software).
          </li>
          <li>
            You may preview the judge forms, but make sure to use the correct form of your track
            when judging.
          </li>
        </ul>
      </section>
    </div>
  );
};
