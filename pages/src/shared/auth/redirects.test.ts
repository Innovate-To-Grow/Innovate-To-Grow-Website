import {describe, expect, it} from 'vitest';

import {buildCompleteProfilePath, getEmailAuthSourcePath, getPostAuthPath} from './redirects';

describe('auth redirects', () => {
  it('builds a complete-profile URL with a safe returnTo', () => {
    expect(buildCompleteProfilePath('/event-registration')).toBe('/complete-profile?returnTo=%2Fevent-registration');
  });

  it('prefers complete-profile when the auth response requires profile completion', () => {
    expect(getPostAuthPath({
      next_step: 'complete_profile',
      requires_profile_completion: true,
      redirect_to: '/schedule',
    })).toBe('/complete-profile');
  });

  it('falls back to a safe redirect when profile completion is not required', () => {
    expect(getPostAuthPath({
      next_step: 'account',
      requires_profile_completion: false,
      redirect_to: '/schedule',
    })).toBe('/schedule');
  });

  it('routes subscribe email links into the profile step when completion is required', () => {
    expect(getEmailAuthSourcePath('subscribe', {
      next_step: 'complete_profile',
      requires_profile_completion: true,
      redirect_to: '/schedule',
    })).toBe('/subscribe?step=profile');
  });

  it('routes incomplete event registration email links through complete-profile first', () => {
    expect(getEmailAuthSourcePath('event_registration', {
      next_step: 'complete_profile',
      requires_profile_completion: true,
      redirect_to: '/schedule',
    })).toBe('/complete-profile?returnTo=%2Fevent-registration');
  });

  it('routes complete event registration email links back to the registration page', () => {
    expect(getEmailAuthSourcePath('event_registration', {
      next_step: 'account',
      requires_profile_completion: false,
      redirect_to: '/schedule',
    })).toBe('/event-registration');
  });
});
