import { useState } from 'react';
import { signup, type SignupFormData } from '../services/api';
import './SignupPage.css';

export const SignupPage = () => {
  const [formData, setFormData] = useState<SignupFormData>({
    first_name: '',
    last_name: '',
    primary_email: '',
    confirm_primary_email: '',
    subscribe_primary_email: false,
    secondary_email: '',
    confirm_secondary_email: '',
    subscribe_secondary_email: false,
    phone_number: '',
    confirm_phone_number: '',
    subscribe_phone: false,
  });

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }));
    // Clear error for this field when user starts typing
    if (errors[name]) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
  };

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formData.first_name.trim()) {
      newErrors.first_name = 'First name is required';
    }

    if (!formData.last_name.trim()) {
      newErrors.last_name = 'Last name is required';
    }

    if (!formData.primary_email.trim()) {
      newErrors.primary_email = 'Primary email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.primary_email)) {
      newErrors.primary_email = 'Invalid email format';
    }

    if (!formData.confirm_primary_email.trim()) {
      newErrors.confirm_primary_email = 'Please confirm your primary email';
    } else if (formData.primary_email !== formData.confirm_primary_email) {
      newErrors.confirm_primary_email = 'Primary emails do not match';
    }

    if (formData.secondary_email && !formData.confirm_secondary_email) {
      newErrors.confirm_secondary_email = 'Please confirm your secondary email';
    } else if (formData.secondary_email && formData.confirm_secondary_email) {
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.secondary_email)) {
        newErrors.secondary_email = 'Invalid email format';
      } else if (formData.secondary_email !== formData.confirm_secondary_email) {
        newErrors.confirm_secondary_email = 'Secondary emails do not match';
      }
    }

    if (formData.phone_number && !formData.confirm_phone_number) {
      newErrors.confirm_phone_number = 'Please confirm your phone number';
    } else if (formData.phone_number && formData.confirm_phone_number) {
      if (formData.phone_number !== formData.confirm_phone_number) {
        newErrors.confirm_phone_number = 'Phone numbers do not match';
      }
    }

    if (!formData.secondary_email && !formData.phone_number) {
      newErrors.phone_number = 'At least one secondary contact (secondary email or phone number) is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!validateForm()) {
      return;
    }

    setLoading(true);

    try {
      const submitData: SignupFormData = {
        first_name: formData.first_name.trim(),
        last_name: formData.last_name.trim(),
        primary_email: formData.primary_email.trim(),
        confirm_primary_email: formData.confirm_primary_email.trim(),
        subscribe_primary_email: formData.subscribe_primary_email,
        subscribe_secondary_email: formData.subscribe_secondary_email,
        subscribe_phone: formData.subscribe_phone,
      };

      if (formData.secondary_email) {
        submitData.secondary_email = formData.secondary_email.trim();
        submitData.confirm_secondary_email = formData.confirm_secondary_email?.trim();
      }

      if (formData.phone_number) {
        submitData.phone_number = formData.phone_number.trim();
        submitData.confirm_phone_number = formData.confirm_phone_number?.trim();
      }

      await signup(submitData);
      setSuccess(true);
    } catch (err: any) {
      if (err.response?.data) {
        const errorData = err.response.data;
        if (typeof errorData === 'object') {
          // Check for general 'error' key first
          if (errorData.error) {
            setErrorMessage(errorData.error);
          } else if (errorData.non_field_errors) {
            // Handle non-field errors
            setErrorMessage(Array.isArray(errorData.non_field_errors) 
              ? errorData.non_field_errors[0] 
              : errorData.non_field_errors);
          } else {
            // Handle field-specific errors
            const fieldErrors: Record<string, string> = {};
            Object.keys(errorData).forEach(key => {
              if (Array.isArray(errorData[key])) {
                fieldErrors[key] = errorData[key][0];
              } else {
                fieldErrors[key] = errorData[key];
              }
            });
            setErrors(fieldErrors);
          }
        } else {
          // String error response
          setErrorMessage(errorData);
        }
      } else {
        setErrorMessage('An error occurred. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="signup-container">
        <div className="signup-success">
          <h1>Signup Successful!</h1>
          <p>Thank you for signing up. Please check your email(s) for verification links.</p>
          <p>You will need to verify your email address(es) to complete your registration.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="signup-container">
      <div className="signup-form-wrapper">
        <h1>Sign Up</h1>
        <form onSubmit={handleSubmit} className="signup-form">
          <div className="form-group">
            <label htmlFor="first_name">First Name *</label>
            <input
              type="text"
              id="first_name"
              name="first_name"
              value={formData.first_name}
              onChange={handleChange}
              required
            />
            {errors.first_name && <span className="error">{errors.first_name}</span>}
          </div>

          <div className="form-group">
            <label htmlFor="last_name">Last Name *</label>
            <input
              type="text"
              id="last_name"
              name="last_name"
              value={formData.last_name}
              onChange={handleChange}
              required
            />
            {errors.last_name && <span className="error">{errors.last_name}</span>}
          </div>

          <div className="form-group">
            <label htmlFor="primary_email">Primary Email *</label>
            <input
              type="email"
              id="primary_email"
              name="primary_email"
              value={formData.primary_email}
              onChange={handleChange}
              required
            />
            {errors.primary_email && <span className="error">{errors.primary_email}</span>}
          </div>

          <div className="form-group">
            <label htmlFor="confirm_primary_email">Confirm Primary Email *</label>
            <input
              type="email"
              id="confirm_primary_email"
              name="confirm_primary_email"
              value={formData.confirm_primary_email}
              onChange={handleChange}
              required
            />
            {errors.confirm_primary_email && <span className="error">{errors.confirm_primary_email}</span>}
          </div>

          <div className="form-group checkbox-group">
            <label>
              <input
                type="checkbox"
                name="subscribe_primary_email"
                checked={formData.subscribe_primary_email}
                onChange={handleChange}
              />
              Subscribe to emails (Primary Email)
            </label>
          </div>

          <div className="form-group">
            <label htmlFor="secondary_email">Secondary Email {!formData.phone_number && '*'}</label>
            <input
              type="email"
              id="secondary_email"
              name="secondary_email"
              value={formData.secondary_email}
              onChange={handleChange}
              required={!formData.phone_number}
            />
            {errors.secondary_email && <span className="error">{errors.secondary_email}</span>}
          </div>

          {formData.secondary_email && (
            <>
              <div className="form-group">
                <label htmlFor="confirm_secondary_email">Confirm Secondary Email</label>
                <input
                  type="email"
                  id="confirm_secondary_email"
                  name="confirm_secondary_email"
                  value={formData.confirm_secondary_email}
                  onChange={handleChange}
                />
                {errors.confirm_secondary_email && <span className="error">{errors.confirm_secondary_email}</span>}
              </div>

              <div className="form-group checkbox-group">
                <label>
                  <input
                    type="checkbox"
                    name="subscribe_secondary_email"
                    checked={formData.subscribe_secondary_email}
                    onChange={handleChange}
                  />
                  Subscribe to emails (Secondary Email)
                </label>
              </div>
            </>
          )}

          <div className="form-group">
            <label htmlFor="phone_number">Phone Number {!formData.secondary_email && '*'}</label>
            <input
              type="tel"
              id="phone_number"
              name="phone_number"
              value={formData.phone_number}
              onChange={handleChange}
              placeholder="+1234567890"
              required={!formData.secondary_email}
            />
            {errors.phone_number && <span className="error">{errors.phone_number}</span>}
          </div>

          {formData.phone_number && (
            <>
              <div className="form-group">
                <label htmlFor="confirm_phone_number">Confirm Phone Number</label>
                <input
                  type="tel"
                  id="confirm_phone_number"
                  name="confirm_phone_number"
                  value={formData.confirm_phone_number}
                  onChange={handleChange}
                  placeholder="+1234567890"
                />
                {errors.confirm_phone_number && <span className="error">{errors.confirm_phone_number}</span>}
              </div>

              <div className="form-group checkbox-group">
                <label>
                  <input
                    type="checkbox"
                    name="subscribe_phone"
                    checked={formData.subscribe_phone}
                    onChange={handleChange}
                  />
                  Subscribe to phone notifications
                </label>
              </div>
            </>
          )}

          {errorMessage && <div className="error-message">{errorMessage}</div>}
          {errors.non_field_errors && <div className="error-message">{errors.non_field_errors}</div>}

          <button type="submit" disabled={loading} className="submit-button">
            {loading ? 'Signing Up...' : 'Sign Up'}
          </button>
        </form>
      </div>
    </div>
  );
};
