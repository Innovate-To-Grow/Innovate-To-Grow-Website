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
  const registrationPage = useEventRegistration();

  if (registrationPage.step === 'loading') {
    return <LoadingState error={registrationPage.error} />;
  }

  if (registrationPage.step === 'done' && registrationPage.registration) {
    return <DoneState registration={registrationPage.registration} />;
  }

  return (
    <div className="event-reg-page">
      <h1 className="event-reg-title">Event Registration</h1>

      {/* Event info banner */}
      {registrationPage.options ? (
        <div className="event-reg-info">
          <h2>{registrationPage.options.name}</h2>
          <p><strong>Date:</strong> {formatEventDate(registrationPage.options.date)}</p>
          <p><strong>Location:</strong> {registrationPage.options.location}</p>
          {registrationPage.options.description ? <p style={{marginTop: '0.5rem'}}>{registrationPage.options.description}</p> : null}
        </div>
      ) : null}

      {registrationPage.error ? <div className="event-reg-alert error">{registrationPage.error}</div> : null}

      {registrationPage.step === 'email' ? (
        <EmailAuthStep
          email={registrationPage.email}
          authLoading={registrationPage.authLoading}
          onEmailChange={registrationPage.setEmail}
          onSubmit={registrationPage.handleEmailSubmit}
        />
      ) : null}

      {registrationPage.step === 'code' ? (
        <CodeVerificationStep
          email={registrationPage.email}
          code={registrationPage.code}
          authFlow={registrationPage.authFlow}
          authLoading={registrationPage.authLoading}
          onCodeChange={registrationPage.setCode}
          onSubmit={registrationPage.handleCodeSubmit}
          onBack={() => {
            registrationPage.setCode('');
            registrationPage.setError(null);
            registrationPage.setStep('email');
          }}
        />
      ) : null}

      {registrationPage.step === 'profile' ? (
        <ProfileStep
          firstName={registrationPage.firstName}
          middleName={registrationPage.middleName}
          lastName={registrationPage.lastName}
          organization={registrationPage.organization}
          saving={registrationPage.saving}
          onFirstNameChange={(value) => {
            registrationPage.setFirstName(value);
            registrationPage.setError(null);
          }}
          onMiddleNameChange={(value) => {
            registrationPage.setMiddleName(value);
            registrationPage.setError(null);
          }}
          onLastNameChange={(value) => {
            registrationPage.setLastName(value);
            registrationPage.setError(null);
          }}
          onOrganizationChange={(value) => {
            registrationPage.setOrganization(value);
            registrationPage.setError(null);
          }}
          onSubmit={registrationPage.handleProfileSubmit}
        />
      ) : null}

      {registrationPage.step === 'form' && registrationPage.options ? (
        <RegistrationFormStep
          options={registrationPage.options}
          selectedTicketId={registrationPage.selectedTicketId}
          answers={registrationPage.answers}
          submitting={registrationPage.submitting}
          attendeeFirstName={registrationPage.attendeeFirstName}
          attendeeLastName={registrationPage.attendeeLastName}
          attendeeSecondaryEmail={registrationPage.attendeeSecondaryEmail}
          attendeePhone={registrationPage.attendeePhone}
          phoneRegion={registrationPage.phoneRegion}
          onFirstNameChange={registrationPage.setAttendeeFirstName}
          onLastNameChange={registrationPage.setAttendeeLastName}
          onTicketChange={registrationPage.setSelectedTicketId}
          onAnswerChange={(questionId, answer) => registrationPage.setAnswers((current) => ({...current, [questionId]: answer}))}
          onSecondaryEmailChange={registrationPage.setAttendeeSecondaryEmail}
          onPhoneChange={registrationPage.setAttendeePhone}
          onPhoneRegionChange={registrationPage.setPhoneRegion}
          phoneCode={registrationPage.phoneCode}
          phoneCodeSent={registrationPage.phoneCodeSent}
          phoneSending={registrationPage.phoneSending}
          phoneVerified={registrationPage.phoneVerified}
          verifyingPhone={registrationPage.verifyingPhone}
          onPhoneCodeChange={registrationPage.setPhoneCode}
          onSendPhoneCode={registrationPage.handleSendPhoneCode}
          onVerifyPhoneCode={registrationPage.handleVerifyPhoneCode}
          onSubmit={registrationPage.handleRegistrationSubmit}
        />
      ) : null}

    </div>
  );
};
