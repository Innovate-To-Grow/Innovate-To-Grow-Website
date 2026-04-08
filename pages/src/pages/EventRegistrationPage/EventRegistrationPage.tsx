import {CodeVerificationStep} from './steps/CodeVerificationStep';
import {DoneState} from './steps/DoneState';
import {EmailAuthStep} from './steps/EmailAuthStep';
import {formatEventDate} from './steps/helpers';
import {LoadingState} from './steps/LoadingState';
import {ProfileStep} from './steps/ProfileStep';
import {RegistrationFormStep} from './steps/RegistrationFormStep';
import {useEventRegistration} from './useEventRegistration';
import './EventRegistrationPage.css';

export const EventRegistrationPage = () => {
  const reg = useEventRegistration();

  if (reg.step === 'done' && reg.registration) {
    return <DoneState registration={reg.registration} />;
  }

  // Fatal: no event payload and we only have an error (e.g. no live event for authenticated bootstrap)
  if (reg.step === 'loading' && reg.error && !reg.options) {
    return <LoadingState error={reg.error} />;
  }

  const bootLoading = reg.step === 'loading' && !reg.options && !reg.error;
  const routingLoading = reg.step === 'loading' && Boolean(reg.options);

  return (
    <div className="event-reg-page">
      <h1 className="event-reg-title">Event Registration</h1>

      {reg.options ? (
        <div className="event-reg-info">
          <h2>{reg.options.name}</h2>
          <p>
            <strong>Date:</strong> {formatEventDate(reg.options.date)}
          </p>
          <p>
            <strong>Location:</strong> {reg.options.location}
          </p>
          {reg.options.description ? <p style={{marginTop: '0.5rem'}}>{reg.options.description}</p> : null}
        </div>
      ) : null}

      {bootLoading ? <div className="event-reg-loading">Loading event details...</div> : null}

      {routingLoading ? <div className="event-reg-loading event-reg-loading--inline">Loading registration form...</div> : null}

      {reg.error ? <div className="event-reg-alert error">{reg.error}</div> : null}

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

      {reg.step === 'profile' ? (
        <ProfileStep
          firstName={reg.firstName}
          middleName={reg.middleName}
          lastName={reg.lastName}
          organizationType={reg.organizationType}
          organization={reg.organization}
          saving={reg.saving}
          onFirstNameChange={(value) => {
            reg.setFirstName(value);
            reg.setError(null);
          }}
          onMiddleNameChange={(value) => {
            reg.setMiddleName(value);
            reg.setError(null);
          }}
          onLastNameChange={(value) => {
            reg.setLastName(value);
            reg.setError(null);
          }}
          onOrganizationTypeChange={(value) => {
            reg.setOrganizationType(value);
            reg.setOrganization('');
            reg.setError(null);
          }}
          onOrganizationChange={(value) => {
            reg.setOrganization(value);
            reg.setError(null);
          }}
          onSubmit={reg.handleProfileSubmit}
        />
      ) : null}

      {reg.step === 'form' && reg.options ? (
        <RegistrationFormStep
          options={reg.options}
          selectedTicketId={reg.selectedTicketId}
          answers={reg.answers}
          submitting={reg.submitting}
          hideAttendeeInfo={reg.profileCompleted}
          attendeeFirstName={reg.attendeeFirstName}
          attendeeLastName={reg.attendeeLastName}
          attendeeOrgType={reg.attendeeOrgType}
          attendeeOrganization={reg.attendeeOrganization}
          attendeeSecondaryEmail={reg.attendeeSecondaryEmail}
          attendeePhone={reg.attendeePhone}
          primaryEmail={reg.primaryEmail}
          accountInfoLocked={reg.accountInfoLocked}
          accountSecondaryEmailLocked={reg.accountSecondaryEmailLocked}
          accountPhoneLocked={reg.accountPhoneLocked}
          phoneRegion={reg.phoneRegion}
          onFirstNameChange={reg.setAttendeeFirstName}
          onLastNameChange={reg.setAttendeeLastName}
          onOrgTypeChange={(value) => {
            reg.setAttendeeOrgType(value);
            reg.setAttendeeOrganization('');
          }}
          onOrganizationChange={reg.setAttendeeOrganization}
          onTicketChange={reg.setSelectedTicketId}
          onAnswerChange={(questionId, answer) => reg.setAnswers((current) => ({...current, [questionId]: answer}))}
          onSecondaryEmailChange={reg.setAttendeeSecondaryEmail}
          onPhoneChange={reg.handlePhoneChange}
          onPhoneRegionChange={reg.handlePhoneRegionChange}
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
