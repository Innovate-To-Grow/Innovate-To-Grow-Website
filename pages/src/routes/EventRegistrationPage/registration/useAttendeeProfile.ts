import {useCallback, useRef, useState} from 'react';
import type {EventRegistrationOptions} from '@/features/events/api';

export type OrganizationType = 'individual' | 'organization';

interface ProfileSnapshot {
  first_name: string;
  middle_name: string;
  last_name: string;
  organization: string;
  title: string;
}

/** The attendee's name and organization, prefilled from (and written back to) the member profile. */
export function useAttendeeProfile() {
  const [firstName, setFirstName] = useState('');
  const [middleName, setMiddleName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organization, setOrganization] = useState('');
  const [title, setTitle] = useState('');
  const [orgType, setOrgType] = useState<OrganizationType>('organization');
  const initialProfileRef = useRef<ProfileSnapshot | null>(null);

  const reset = useCallback(() => {
    setFirstName('');
    setMiddleName('');
    setLastName('');
    setOrganization('');
    setTitle('');
    setOrgType('organization');
    initialProfileRef.current = null;
  }, []);

  // Pre-fill attendee fields from member profile.
  const prefill = useCallback((data: EventRegistrationOptions) => {
    const profile = data.member_profile;
    if (!profile) return;
    setFirstName(profile.first_name);
    setMiddleName(profile.middle_name);
    setLastName(profile.last_name);
    const org = profile.organization || '';
    const isIndividual = ['individual', 'personal'].includes(org.trim().toLowerCase());
    setOrgType(isIndividual ? 'individual' : 'organization');
    setOrganization(isIndividual ? '' : org);
    setTitle(profile.title || '');
    initialProfileRef.current = {
      first_name: profile.first_name,
      middle_name: profile.middle_name,
      last_name: profile.last_name,
      organization: isIndividual ? 'Individual' : org,
      title: profile.title || '',
    };
  }, []);

  /** The profile as it will be saved: an individual is stored as organization "Individual", without a title. */
  const submittedProfile = (): ProfileSnapshot => ({
    first_name: firstName.trim(),
    middle_name: middleName.trim(),
    last_name: lastName.trim(),
    organization: orgType === 'individual' ? 'Individual' : organization.trim(),
    title: orgType === 'organization' ? title.trim() : '',
  });

  /** Whether the submitted profile differs from the one the form was prefilled with. */
  const profileChanged = (submitted: ProfileSnapshot) => {
    const previous = initialProfileRef.current;
    return (
      !previous ||
      (Object.keys(submitted) as Array<keyof ProfileSnapshot>).some((field) => previous[field] !== submitted[field])
    );
  };

  return {
    firstName,
    setFirstName,
    middleName,
    setMiddleName,
    lastName,
    setLastName,
    organization,
    setOrganization,
    title,
    setTitle,
    orgType,
    setOrgType,
    reset,
    prefill,
    submittedProfile,
    profileChanged,
  };
}
