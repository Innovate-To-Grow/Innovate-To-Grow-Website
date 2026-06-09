import {describe, expect, it} from 'vitest';

import {buildCompleteProfilePath, buildLoginPath, getEmailAuthSourcePath, getPostAuthPath} from '../redirects';

describe('auth redirects', () => {
  it('builds a complete-profile URL with a safe returnTo', () => {
    expect(buildCompleteProfilePath('/event-registration')).toBe('/complete-profile?returnTo=%2Fevent-registration');
  });

  it('prefers complete-profile when the auth response requires profile completion', () => {
    expect(getPostAuthPath({
      next_step: 'complete_profile',
      requires_profile_completion: true,
      redirect_to: '/schedule',
    })).toBe('/complete-profile?returnTo=%2Fschedule');
  });

  it('drops an unsafe redirect_to when detouring through complete-profile', () => {
    expect(getPostAuthPath({
      next_step: 'complete_profile',
      requires_profile_completion: true,
      redirect_to: 'https://evil.example/phish',
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

  it('builds a bare /login path when no returnTo is supplied', () => {
    expect(buildLoginPath()).toBe('/login');
    expect(buildLoginPath('')).toBe('/login');
    expect(buildLoginPath(null)).toBe('/login');
  });

  it('builds /login with an encoded returnTo for a safe internal path', () => {
    expect(buildLoginPath('/past-projects')).toBe('/login?returnTo=%2Fpast-projects');
    expect(buildLoginPath('/past-projects/abc?value=x')).toBe('/login?returnTo=%2Fpast-projects%2Fabc%3Fvalue%3Dx');
  });

  it('drops an unsafe returnTo when building the login path', () => {
    expect(buildLoginPath('https://evil.example/phish')).toBe('/login');
    expect(buildLoginPath('//evil.example')).toBe('/login');
  });

  it('prefers a page returnTo over the backend redirect_to after login', () => {
    expect(getPostAuthPath(
      {next_step: 'account', requires_profile_completion: false, redirect_to: '/account'},
      '/past-projects',
    )).toBe('/past-projects');
  });

  it('preserves a page returnTo through the complete-profile detour', () => {
    expect(getPostAuthPath(
      {next_step: 'complete_profile', requires_profile_completion: true, redirect_to: '/schedule'},
      '/past-projects',
    )).toBe('/complete-profile?returnTo=%2Fpast-projects');
  });

  it('ignores an unsafe returnTo and falls back to a safe redirect_to', () => {
    expect(getPostAuthPath(
      {next_step: 'account', requires_profile_completion: false, redirect_to: '/schedule'},
      '//evil.example',
    )).toBe('/schedule');
  });

  it('falls back to /account when neither returnTo nor redirect_to is safe', () => {
    expect(getPostAuthPath(
      {next_step: 'account', requires_profile_completion: false, redirect_to: ''},
      null,
    )).toBe('/account');
  });
});
