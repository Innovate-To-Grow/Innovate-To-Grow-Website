import { Link } from 'react-router-dom';
import './SponsorAcknowledgementPage.css';

export const SponsorAcknowledgementPage = () => {
  return (
    <div className="sponsor-ack-page">
      <h1 className="sponsor-ack-page-title">I2G Project Sponsor Acknowledgement</h1>

      <p className="sponsor-ack-text sponsor-ack-center">
        <strong>University of California, Merced - School of Engineering - Innovate to Grow Program</strong>
      </p>

      <p className="sponsor-ack-text sponsor-ack-center">
        <strong>Partner Acknowledgement</strong>
      </p>

      {/* Summary */}
      <h2 className="sponsor-ack-section-title">Summary</h2>

      <p className="sponsor-ack-text"><em>Partner</em>:</p>
      <ul className="sponsor-ack-list">
        <li>
          Partner must assign a knowledgeable liaison/mentor for the project duration.
        </li>
        <li>
          The liaison/mentor must be present at project kick-off to provide a thorough understanding
          of the project goals. Without sufficient information students may be unable to move forward
          quickly. (After kick-off the when and how of interactions can be discussed with the team).
        </li>
        <li>
          If Partner is unresponsive or decides to pull-out in the middle of a project, it accepts
          that students can continue on that project, otherwise they may be affected significantly,
          both academically and financially.
        </li>
      </ul>

      <p className="sponsor-ack-text"><em>Students</em>:</p>
      <ul className="sponsor-ack-list">
        <li>
          Students will digitally sign agreements (NDA and IP licensing) to the Partners, before
          accessing the list of partner projects.
        </li>
        <li>
          Students unwilling to do so will be assigned to a project that does not require NDA or IP
          assignment to Partner.
        </li>
      </ul>

      <p className="sponsor-ack-text"><em>UC Merced</em>:</p>
      <ul className="sponsor-ack-list">
        <li>UCM matches students with approved Partner projects, forming teams.</li>
        <li>UCM does not retain IP. See student section above.</li>
        <li>UCM does not guarantee delivery of results, and requires liability indemnification.</li>
        <li>
          UCM does not require payment as a condition to run a Partner project, but seeks and
          appreciates donations to sustain the program.
        </li>
      </ul>

      {/* Notice */}
      <p className="sponsor-ack-text">
        <em>Notice</em>: Special circumstances can be discussed during the course of the project to
        ensure success for all parties involved (Win-Win-Win). This includes specific project
        requirements such as confidentiality, IP, access to facilities, material and equipment costs,
        levels of support to the program, etc.
      </p>

      {/* I2G Program Background */}
      <h2 className="sponsor-ack-section-title">I2G Program Background</h2>

      <p className="sponsor-ack-text">
        Thank you for your interest in supporting UC Merced's Innovate to Grow (I2G) Program. The
        primary objective of the Program is to provide UC Merced (UCM) undergraduate students with
        the opportunity to learn as part of a team that includes practicing engineers and other
        professionals from partner organizations like yours (Partner). I2G projects are undertaken by
        students from engineering and other participating majors as the final part of their degree
        requirements. The I2G teams focus on design projects with engineering content that are chosen
        purposefully based on their potential for desirable near-term impact on Partners' needs/goals.
        As such, the commitment of the teams and partners greatly enhances the quality of the design
        experience over traditional academic projects required by accredited engineering degree
        curricula. It adds significant professional training with real-world implications for the
        students. Your mentorship of I2G students in addition to financial and resource commitment
        will support and enhance UCM's educational mission and the experience of its students.
      </p>

      <p className="sponsor-ack-text">
        Since I2G is an educational program, UCM does not retain intellectual property (IP), and does
        not guarantee completion of any project or delivery of any project results, although based on
        previous experience we expect a high level of effort and productivity from our students. It is
        important that you understand that the I2G Program is an academic program designed to meet the
        requirements of the students' academic program and that any benefit to the Partner in terms of
        the outcome of the research is an important, yet secondary, purpose and objectives of the
        Program.
      </p>

      <p className="sponsor-ack-text">
        The remainder of this acknowledgement form explains the details of the Partners' collaboration
        in I2G and its Projects. We ask that you acknowledge your understanding of the purpose and
        elements of the I2G Program.
      </p>

      {/* Section 1 */}
      <p className="sponsor-ack-numbered-title">1. Project Mentorship and Liaison Expectations</p>

      <p className="sponsor-ack-text">
        The sponsoring organization is requested to identify an employee of your organization to act
        as liaison/mentor for your project(s). This liaison/mentor should plan to meet (in person or
        via teleconference) with students assigned to your project(s) on a regular basis, and with UCM
        faculty responsible for academic supervision of the project(s) as necessary. The interaction
        between the liaison/mentor and the team is advised on a weekly or bi-weekly basis to answer
        questions and ensure team progress.
      </p>

      <p className="sponsor-ack-text">
        Notice: It is important that the Partner's liaison/mentor responds promptly to the students at
        the beginning of the semester to provide detail and clarifications about the project and its
        objectives, so that the team begins the project quickly and in the right direction.
        Communications thereafter can be arranged between the mentor and team.
      </p>

      {/* Section 2 */}
      <p className="sponsor-ack-numbered-title">2. Intellectual Property</p>

      <p className="sponsor-ack-text">
        Students participating in the I2G Program are not employees of the University. Per UC's Patent
        Policy, the University will not own any patentable ideas and inventions, copyrights, data, or
        other intellectual property developed by students while performing a I2G Project.
      </p>

      <p className="sponsor-ack-text">
        The <Link to="/student-agreement">I2G Student Agreement</Link> that students sign to
        participate in a sponsored I2G Project includes the provision to assign to its sponsor a
        non-exclusive, transferable, sub-licensable, royalty-free, worldwide license to use the
        intellectual property developed as part of the I2G Project.
      </p>

      <p className="sponsor-ack-text">
        If a student does not wish to execute an assignment of rights, the student will have the
        opportunity to work on an alternative or academic project that does not require IP assignment,
        and another student will be assigned to the sponsored I2G Project.
      </p>

      <p className="sponsor-ack-text">
        UCM employees, including faculty and staff, will not participate as part of the project except
        in the capacity as academic advisors to the student participants.
      </p>

      {/* Section 3 */}
      <p className="sponsor-ack-numbered-title">3. Financial Expectations</p>

      <p className="sponsor-ack-text">
        A financial commitment is not mandatory. However, we welcome and encourage donations to the UC
        Merced School of Engineering I2G program. Such funds enable the School to support this
        program, including all associated initiatives and events. If your organization would like to
        make a tax-deductible charitable gift to support operation of the overall Program you may{' '}
        <a
          href="https://securelb.imodules.com/s/1650/index.aspx?sid=1650&gid=1&pgid=474&utm_source=give_now_button&utm_medium=give_now_button&utm_campaign=uc_merced_giving"
          target="_blank"
          rel="noopener noreferrer"
        >
          click here to donate now
        </a>{' '}
        or contact the UC Merced Staff for additional information (
        <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>). UCM will use gifts from you and
        other sponsors to cover the general costs and expenses associated with the I2G Program and
        Event (including staff time, engineering and administrative support, UC's standard 5 percent
        gift assessment, travel by students and staff to partner sites for visits / presentations,
        parts and expendable supplies for projects, and competition prizes).
      </p>

      <p className="sponsor-ack-text">
        The School provides each Team with a basic budget for material and travel. However, if a
        proposed project exceeds the available University resources needed to study, design, prototype
        or test the solution, then we encourage you to propose an alternative or revised project with
        corresponding resource budgets, or to provide additional resources to support the objectives of
        the project. If it is anticipated that any of your projects will incur any extraordinary
        expenses (for example specialized equipment), necessary arrangements will be negotiated in
        advance of the commencement of work on your project and will be subject to a specific written
        agreement of UCM and your organization.
      </p>

      {/* Section 4 */}
      <p className="sponsor-ack-numbered-title">4. I2G Projects Suitability and Students Assignment</p>

      <p className="sponsor-ack-text">
        We anticipate that your organization may wish to propose one or more projects that address your
        organization's needs or problems, seeking viable design solutions developed by our student
        teams that may be deployed (see Intellectual property section). UCM will work with you to
        define or refine a problem/project statements that are simultaneously suitable for an I2G
        Project per professional degree requirements, policies, and departmental standards. As the I2G
        Projects progress, we will continue to work together to address any desired changes to
        projects.
      </p>

      <p className="sponsor-ack-text">
        UCM will assign a group of undergraduate engineering and other students to a project, if there
        are enough students with expertise/majors that elect to participate in the project. If there is
        no match, the project may be reconsidered for execution in the following semester.
      </p>

      {/* Section 5 */}
      <p className="sponsor-ack-numbered-title">5. Presentations, Confidentiality</p>

      <p className="sponsor-ack-text">
        The University is committed to maintaining an open academic environment that fosters
        intellectual creativity. Please be aware that the students and advising faculty members will
        freely discuss all non-confidential information associated with your project as part of the
        normal educational activities of the Program. As part of I2G Projects, the students will make
        various reports and presentations to other members of the I2G Program as part of the
        educational experience. Students also may wish to include information about their I2G Projects
        in their resumes, applications and other documents.
      </p>

      <p className="sponsor-ack-text">
        We realize that the students working on your project may come into contact with your
        proprietary or confidential information in the course of the project. Therefore, all students
        participating in the I2G Program execute a general non-disclosure agreement (NDA) relating to
        confidential and proprietary information prior to their participation in the Program (included
        in the <Link to="/student-agreement">I2G Student Agreement</Link>). If you wish to have the
        participants undertaking your project execute a specific non-disclosure agreement of your
        organization, you should provide a copy of your organization NDA prior to disclosing
        confidential information to the participants, and send a copy to{' '}
        <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>. If a student does not wish to execute
        your NDA, the student will have the opportunity to work on another project and another student
        will be assigned to your project. Please keep in mind that during the course of your project,
        you will need to clearly identify for students what constitutes or is likely to constitute
        proprietary or confidential information.
      </p>

      <p className="sponsor-ack-text">
        Your organization hereby releases the University, its officers, employees, students and agents
        from any and all liability, loss, expense (including reasonable attorneys' fees), or claims for
        injury or damages arising out of the released parties' disclosure of any proprietary or
        confidential information, except to the extent the released party intentionally disclosed
        information that such released party knew to be proprietary/confidential. The foregoing release
        shall not limit your right to obtain legally permissible relief pursuant to the terms of any
        NDA entered into directly between you and any student, faculty or staff.
      </p>

      {/* Section 6 */}
      <p className="sponsor-ack-numbered-title">6. No Warranties</p>

      <p className="sponsor-ack-text">
        The University makes no warranties, express or implied, as to the condition, accuracy,
        originality, merchantability, or fitness for purposes of any products, processes or
        intellectual property developed in the I2G Program.
      </p>

      {/* Section 7 */}
      <p className="sponsor-ack-numbered-title">7. No License Granted</p>

      <p className="sponsor-ack-text">
        Other than as may be required to implement the I2G Program as part of the educational
        experience of UCM students, this acknowledgement does not constitute a grant of license,
        either implied or express, of any intellectual property owned or acquired by your organization,
        to the University, or anyone associated therewith, including its officers, employees, students
        and agents. UCM has the right to retain non-confidential items relating to your project for
        educational purposes, including copies of any software, records, project notebooks, memoranda,
        information, data, programs, models and equipment.
      </p>

      {/* Section 8 */}
      <p className="sponsor-ack-numbered-title">8. Compliance with All Laws</p>

      <p className="sponsor-ack-text">
        All work on your project must be carried out in compliance with federal and state laws and
        regulations and applicable policies (i.e., University policies and/or your organization's
        policies), including laws, regulations and policies relating to environmental and occupational
        health and safety. Your organization and UCM are responsible for ensuring such compliance in
        their respective facilities.
      </p>

      {/* Section 9 */}
      <p className="sponsor-ack-numbered-title">9. Affiliation Agreement and Release of Liability</p>

      <p className="sponsor-ack-text">
        We assume that your organization may have an affiliation agreement and/or release of liability
        that you require individuals working in your facilities to execute before entering the facility
        or commencing work. For that reason, we will inform all students who are assigned to the I2G
        Program of this likelihood. You should provide a copy of the requested affiliation agreement
        and/or release of liability for signature to the students selected to work on your project
        before entering your facilities, and send a copy to{' '}
        <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>. If the student does not wish to
        execute the affiliation agreement or release, the student will be moved to an alternative UCM
        academic project and another student will be assigned to your project.
      </p>

      {/* Section 10 */}
      <p className="sponsor-ack-numbered-title">10. Release of Liability and Indemnification</p>

      <p className="sponsor-ack-text">
        In consideration of your participation in the I2G Program, you agree to release the
        University, its officers, employees, students and agents, from any claims arising out of the
        originality, design, manufacture, or use of any of the products, processes, technologies, or
        intellectual property generated as a result of the project, unless such claims arise out of
        the willful misconduct or gross negligence of UC Merced, its officers, employees, students and
        agents. You agree that the University will not be liable for incidental or consequential
        damages, or for loss of profits, resulting from the work undertaken on your project or any
        breach of this agreement.
      </p>

      {/* Section 11 */}
      <p className="sponsor-ack-numbered-title">11. Use of Name</p>

      <p className="sponsor-ack-text">
        Please understand that California law restricts the use of University of California names and
        trademarks. Therefore, if you have the need to use these names and trademarks in connection
        with this collaboration, you will need to submit a written request for the University's
        approval. Please be aware that the names and trademarks of the University may not be used for
        any commercial purpose. UCM will request your approval before using your name and trademarks.
      </p>

      {/* Section 12 */}
      <p className="sponsor-ack-numbered-title">12. Term</p>

      <p className="sponsor-ack-text">
        While you may terminate your participation in the I2G Project by providing UCM with at least
        thirty (30) days prior written notice, however, please be aware that early termination will
        have a significant effect on the students' academic program. We encourage you to explore with
        UCM ways to complete the project before terminating your participation. In order to ensure that
        the students' academic experience is not adversely affected, the University reserves the right
        to continue the project to the extent possible to allow the student to complete their program.
        In this event, the students may or may not share the results or outcomes of the project with
        you, in their sole discretion.
      </p>

      {/* Acknowledgement */}
      <h2 className="sponsor-ack-section-title">Acknowledgement</h2>

      <p className="sponsor-ack-text">
        If the terms of this letter meet your approval, please acknowledge your organization's
        participation subject to the expectations and terms of the I2G Program.
      </p>

      <p className="sponsor-ack-text">
        Your acknowledgement may be executed in one of the following ways:
      </p>

      <p className="sponsor-ack-text">
        <strong>Project submission system:</strong> accepting these terms by submitting a project in
        the <Link to="/project-submission">I2G project submission system</Link>.
      </p>

      <p className="sponsor-ack-text">
        <strong>Email acknowledgement:</strong> express your acknowledgement in an email, in response
        to the email your organization received containing your project(s) information along with all
        IP+NDA Agreements of the Students working on your project(s).
      </p>

      <p className="sponsor-ack-text">
        <strong>Signed acknowledgement:</strong> sign or digitally sign a copy of this document, and
        send a scanned copy or PDF to <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.
      </p>

      <p className="sponsor-ack-text">
        We appreciate your support of and participation in the I2G Program and look forward to your
        collaboration with our students.
      </p>
    </div>
  );
};
