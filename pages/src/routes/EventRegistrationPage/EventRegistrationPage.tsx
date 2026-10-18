import {CodeVerificationStep} from './steps/CodeVerificationStep';
import {DoneState} from './steps/DoneState';
import {EmailAuthStep} from './steps/EmailAuthStep';
import {EventSelectionStep} from './steps/EventSelectionStep';
import {formatEventDateRange} from '@/features/events/formatEventDateRange';
import {LoadingState} from './steps/LoadingState';
import {RegistrationFormStep} from './steps/RegistrationFormStep';
import {getRegistrationStepIndex} from './steps/helpers';
import {RegistrationSteps} from './steps/RegistrationSteps';
import {useEventRegistration} from './useEventRegistration';

export const EventRegistrationPage = () => {
  const reg = useEventRegistration();
  const stepIndex = getRegistrationStepIndex(reg.step);

  if (reg.step === 'done' && reg.registration) {
    return (
      <div className="event-reg-page">
        <h1 className="itg-page-title event-reg-title">Event Registration</h1>
        {stepIndex !== null ? <RegistrationSteps current={stepIndex} /> : null}
        <DoneState
          registration={reg.registration}
          showChooseAnother={reg.events.length > 1}
          onChooseAnother={reg.handleShowEventList}
        />
      </div>
    );
  }

  // Fatal: no event payload and we only have an error (e.g. no live event for authenticated bootstrap)
  if (reg.step === 'loading' && reg.error && !reg.options) {
    return <LoadingState error={reg.error} />;
  }

  const bootLoading = reg.step === 'loading' && !reg.options && !reg.error;
  const routingLoading = reg.step === 'loading' && Boolean(reg.options);

  return (
    <div className="event-reg-page">
      <h1 className="itg-page-title event-reg-title">Event Registration</h1>

      {stepIndex !== null ? <RegistrationSteps current={stepIndex} /> : null}

      {reg.options ? (
        <section className="event-reg-info" aria-labelledby="event-reg-info-title">
          <h2 id="event-reg-info-title" className="itg-section-title event-reg-info-title">
            {reg.options.name}
          </h2>
          <dl className="itg-meta-box event-reg-info-meta">
            <div className="itg-meta-item">
              <dt className="itg-meta-label">Date</dt>
              <dd className="itg-meta-value">{formatEventDateRange(reg.options.date, reg.options.end_date)}</dd>
            </div>
            <div className="itg-meta-item">
              <dt className="itg-meta-label">Location</dt>
              <dd className="itg-meta-value">{reg.options.location || 'TBA'}</dd>
            </div>
          </dl>
          {reg.options.description ? <p className="event-reg-info-description">{reg.options.description}</p> : null}
        </section>
      ) : null}

      {bootLoading ? <p className="event-reg-loading" role="status">Loading event details...</p> : null}

      {routingLoading ? (
        <p className="event-reg-loading event-reg-loading--inline" role="status">Loading registration form...</p>
      ) : null}

      {reg.error ? <div className="event-reg-alert error" role="alert">{reg.error}</div> : null}

      {reg.step === 'select' ? (
        <EventSelectionStep
          events={reg.events}
          selectedEventSlug={reg.selectedEventSlug}
          onSelect={reg.handleSelectEvent}
        />
      ) : null}

      {reg.step === 'email' ? (
        <EmailAuthStep
          email={reg.email}
          authLoading={reg.authLoading}
          onEmailChange={reg.setEmail}
          onSubmit={reg.handleEmailSubmit}
        />
      ) : null}

      {reg.step === 'code' ? (
        <CodeVerificationStep
          email={reg.email}
          code={reg.code}
          authLoading={reg.authLoading}
          onCodeChange={reg.setCode}
          onSubmit={reg.handleCodeSubmit}
          onBack={() => {
            reg.setCode('');
            reg.setError(null);
            reg.setStep('email');
          }}
        />
      ) : null}

      {reg.step === 'form' && reg.options ? (
        <RegistrationFormStep
          options={reg.options}
          selectedTicketId={reg.selectedTicketId}
          answers={reg.answers}
          submitting={reg.submitting}
          attendeeFirstName={reg.attendeeFirstName}
          attendeeMiddleName={reg.attendeeMiddleName}
          attendeeLastName={reg.attendeeLastName}
          attendeeOrgType={reg.attendeeOrgType}
          attendeeOrganization={reg.attendeeOrganization}
          attendeeTitle={reg.attendeeTitle}
          attendeeSecondaryEmail={reg.attendeeSecondaryEmail}
          attendeePhone={reg.attendeePhone}
          primaryEmail={reg.primaryEmail}
          phoneError={reg.phoneError}
          onFirstNameChange={reg.setAttendeeFirstName}
          onMiddleNameChange={reg.setAttendeeMiddleName}
          onLastNameChange={reg.setAttendeeLastName}
          onOrgTypeChange={(value) => {
            reg.setAttendeeOrgType(value);
            reg.setAttendeeOrganization('');
            reg.setAttendeeTitle('');
          }}
          onOrganizationChange={reg.setAttendeeOrganization}
          onTitleChange={reg.setAttendeeTitle}
          onTicketChange={reg.setSelectedTicketId}
          onAnswerChange={(questionId, answer) => reg.setAnswers((current) => ({...current, [questionId]: answer}))}
          onSecondaryEmailChange={reg.handleSecondaryEmailChange}
          onPhoneChange={reg.handlePhoneChange}
          secondaryEmailCode={reg.secondaryEmailCode}
          secondaryEmailCodeSent={reg.secondaryEmailCodeSent}
          secondaryEmailSending={reg.secondaryEmailSending}
          secondaryEmailVerified={reg.secondaryEmailVerified}
          verifyingSecondaryEmail={reg.verifyingSecondaryEmail}
          onSecondaryEmailCodeChange={reg.setSecondaryEmailCode}
          onSendSecondaryEmailCode={reg.handleSendSecondaryEmailCode}
          onVerifySecondaryEmailCode={reg.handleVerifySecondaryEmailCode}
          phoneCode={reg.phoneCode}
          phoneCodeSent={reg.phoneCodeSent}
          phoneSending={reg.phoneSending}
          phoneVerified={reg.phoneVerified}
          verifyingPhone={reg.verifyingPhone}
          onPhoneCodeChange={reg.setPhoneCode}
          onSendPhoneCode={reg.handleSendPhoneCode}
          onVerifyPhoneCode={reg.handleVerifyPhoneCode}
          onSubmit={reg.handleRegistrationSubmit}
        />
      ) : null}

    </div>
  );
};
