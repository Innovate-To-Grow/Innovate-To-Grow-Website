import './PurchasingReimbursementPage.css';

export const PurchasingReimbursementPage = () => {
  return (
    <div className="student-page">
      <h1 className="student-page-title">Capstone Purchasing &amp; Reimbursement</h1>

      <section className="student-section">
        <h2 className="student-section-title">Capstone Purchasing Forms</h2>
        <p className="student-text">Forms are dependent on the class.</p>
        <ul className="student-list">
          <li>
            <a
              href="https://soeinstructional.ucmerced.edu/capstone-design/capstone-purchase-request-form-ce-193-dr-robert-rice"
              target="_blank"
              rel="noopener noreferrer"
            >
              Capstone Purchase Request Form - CE 193
            </a>
          </li>
          <li>
            <a
              href="https://soeinstructional.ucmerced.edu/capstone-design/capstone-purchase-request-form-cse-120-dr-santosh-chandrasekhar"
              target="_blank"
              rel="noopener noreferrer"
            >
              Capstone Purchase Request Form - CSE 120
            </a>
          </li>
          <li>
            <a
              href="https://soeinstructional.ucmerced.edu/capstone-design/capstone-purchase-request-form-engr-193-dr-alejandro-guti%C3%A9rrez"
              target="_blank"
              rel="noopener noreferrer"
            >
              Capstone Purchase Request Form - ENGR 193
            </a>
          </li>
          <li>
            <a
              href="https://soeinstructional.ucmerced.edu/capstone-design/capstone-purchase-request-form-engr-194-dr-alejandro-guti%C3%A9rrez"
              target="_blank"
              rel="noopener noreferrer"
            >
              Capstone Purchase Request Form - ENGR 194
            </a>
          </li>
        </ul>
        <p className="student-text">
          For more information, please visit the{' '}
          <a
            href="https://soeinstructional.ucmerced.edu/capstone-design"
            target="_blank"
            rel="noopener noreferrer"
          >
            SoE-Instructional site for Capstone
          </a>
          .
        </p>
      </section>

      <section className="student-section">
        <h2 className="student-section-title">
          Reimbursement for Travel and Small Expenses
        </h2>
        <p className="student-text">
          To submit a request for reimbursement, please first read the instructions provided in
          your class announcements and the guidelines below, and submit this form when the
          information is correct and complete:
        </p>
        <ul className="student-list">
          <li>
            <a
              href="https://forms.gle/AKgT3CcRLoKBa6W8A"
              target="_blank"
              rel="noopener noreferrer"
            >
              I2G-Capstone-Reimbursement Form
            </a>
          </li>
          <li>
            <a
              href="https://drive.google.com/file/d/1pexXU8lxx6-_j5iiMxUtDb5oCGZjiXWP/view?usp=sharing"
              target="_blank"
              rel="noopener noreferrer"
            >
              Guidelines for Travel and Small Expenses Reimbursements for Teams in I2G / Capstone
            </a>
          </li>
        </ul>
        <p className="student-text">
          <strong>All teams</strong> (the student in charge of finance / CFO) that need to purchase
          materials or get reimbursed for travel{' '}
          <strong>
            <a
              href="https://drive.google.com/file/d/1pexXU8lxx6-_j5iiMxUtDb5oCGZjiXWP/view?usp=sharing"
              target="_blank"
              rel="noopener noreferrer"
            >
              MUST READ these guidelines
            </a>
          </strong>{' '}
          before entering any forms.
        </p>
      </section>
    </div>
  );
};
