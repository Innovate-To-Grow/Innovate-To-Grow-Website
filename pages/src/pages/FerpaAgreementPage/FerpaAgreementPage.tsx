import './FerpaAgreementPage.css';

export const FerpaAgreementPage = () => {
  return (
    <div className="student-page">
      <h1 className="student-page-title">FERPA Agreement</h1>

      <section className="student-section">
        <h2 className="student-section-title" style={{ textAlign: 'center' }}>
          Student Presentation Permission and FERPA Release
        </h2>

        <p className="student-text">
          I hereby grant to The Regents of the University of California, on behalf of the Merced
          campus, permission to record by means of audio-visual analog and/or digital medium the
          presentation, lecture(s), interviews, and related materials I will prepare and present as
          part of Innovate to Grow ("Presentation") and to reproduce the Presentation, including any
          written materials or visual aid utilized during the Presentation, my name, likeness,
          identity, voice, photographic image, videographic image and oral or recorded statements
          (hereafter "Related Appearance") for research or educational use subject to the following
          restrictions:
        </p>

        <ol className="student-ordered-list">
          <li>
            The Presentation and Related Appearance will be utilized for the program listed above
            only. The material will be available online via a video stream which may be accessed by
            UC Merced staff, faculty, and the general public.
          </li>
          <li>
            The Presentation and Related Appearance will be available online during the event and
            will be subsequently archived for reuse.
          </li>
          <li>
            UC Merced will use the Presentation and Related Appearance for educational purposes only
            and not for any commercial/promotional purposes or activities.
          </li>
        </ol>

        <p className="student-text">
          By signing this form, I waive and release The Regents of the University of California and
          its officers, agents and employees, from any claim or liability relating to the use of the
          Presentation and Related Appearance in conformance with the restrictions stated above.
        </p>

        <p className="student-text">
          <strong>FERPA RELEASE</strong>: I understand that the media may be protected by the
          Federal Educational Rights and Privacy Act ("FERPA") as educational records. I hereby
          consent to the disclosure of the presentation by the University to faculty, staff,
          students, and visitors of the University, which may include the general public. The purpose
          of this disclosure is to advance the educational mission of the University.
        </p>

        <p className="student-text">
          This Agreement shall be governed by and interpreted in accordance with the laws of the
          State of California. This Agreement expresses the complete understanding of the parties
          with respect to the subject matter and supersedes all prior representations and
          understandings.
        </p>

        <p className="student-text">
          I acknowledge that The Regents of the University of California will rely on this
          permission and release in producing and distributing the Presentation and the Related
          Appearance.
        </p>

        <p className="student-text">
          I am an adult, 18 years or older, and I have read and understand this agreement and I
          freely and knowingly give my consent to The Regents of the University of California, on
          behalf of the Merced campus, as described herein.
        </p>
      </section>

      <section className="student-section">
        <p className="student-text">
          <strong>
            If individual photographed/recorded is under eighteen (18) years old, the following
            section must be completed:
          </strong>{' '}
          I have read and I understand this document. I understand and agree that it is binding on
          me, my child (named above), our heirs, assigns and personal representatives. I
          acknowledge that I am eighteen (18) years old or more and that I am the parent or guardian
          of the child named above.
        </p>
      </section>
    </div>
  );
};
