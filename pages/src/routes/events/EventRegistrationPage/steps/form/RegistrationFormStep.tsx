import {useState, type FormEvent} from 'react';
import {PhoneField, SecondaryEmailField} from './ContactFields';
import {getRegistrationFormErrors, hasRegistrationFormErrors} from './formErrors';
import {PersonalInfoFields} from './PersonalInfoFields';
import {RegistrationDetailsFields} from './RegistrationDetailsFields';
import type {FormSectionProps, RegistrationFormStepProps} from './types';

export type {RegistrationFormStepProps};

/** The registration form. Field errors appear once the attendee has tried to submit. */
export const RegistrationFormStep = (props: RegistrationFormStepProps) => {
  const [attempted, setAttempted] = useState(false);
  const errors = getRegistrationFormErrors(props);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    if (hasRegistrationFormErrors(errors)) {
      requestAnimationFrame(() => {
        const firstError = document.querySelector('.event-reg-form-group--error');
        if (firstError && typeof firstError.scrollIntoView === 'function') {
          firstError.scrollIntoView({behavior: 'smooth', block: 'center'});
        }
      });
      return;
    }
    props.onSubmit(e);
  };

  const showError = attempted && !props.submitting;
  const section: FormSectionProps = {
    form: props,
    errors,
    showError,
    errorClass: (condition: boolean) => (showError && condition ? ' event-reg-form-group--error' : ''),
  };

  return (
    <form onSubmit={handleSubmit} noValidate>
      <div className="itg-panel event-reg-section-card">
        <div className="event-reg-section-header">
          <h3 className="event-reg-section-title">Personal Information</h3>
        </div>
        <PersonalInfoFields {...section} />
        <SecondaryEmailField {...section} />
        <PhoneField {...section} />
      </div>

      <div className="itg-panel event-reg-section-card event-reg-section-card--spaced">
        <h3 className="event-reg-section-title">Registration Details</h3>
        <RegistrationDetailsFields {...section} />
      </div>

      <button type="submit" className="itg-btn itg-btn-primary itg-btn-lg event-reg-submit" disabled={props.submitting}>
        {props.submitting ? <><span className="event-reg-spinner" /> Registering...</> : 'Register'}
      </button>
    </form>
  );
};
