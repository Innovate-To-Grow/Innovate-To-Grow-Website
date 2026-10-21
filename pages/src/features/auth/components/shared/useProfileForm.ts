import {useCallback, useState} from 'react';
import type {ProfileResponse} from '@/features/auth/api';

export type OrganizationType = 'individual' | 'organization';

const text = (value: string | null | undefined) => value || '';

/** Organization "Individual"/"Personal" is shown as the Individual choice with no organization name. */
const organizationFields = (organization: string) => {
  const isIndividual = ['individual', 'personal'].includes(organization.trim().toLowerCase());
  return {
    organizationType: (isIndividual ? 'individual' : 'organization') as OrganizationType,
    organization: isIndividual ? '' : organization,
  };
};

/**
 * The editable profile fields (account page and profile completion), filled from a profile, and the
 * update they submit.
 */
export function useProfileForm() {
  const [firstName, setFirstName] = useState('');
  const [middleName, setMiddleName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organization, setOrganization] = useState('');
  const [title, setTitle] = useState('');
  const [organizationType, setOrganizationType] = useState<OrganizationType>('organization');

  const fillForm = useCallback((source: ProfileResponse | null) => {
    const fields = source ?? ({} as Partial<ProfileResponse>);
    setFirstName(text(fields.first_name));
    setMiddleName(text(fields.middle_name));
    setLastName(text(fields.last_name));
    const org = organizationFields(text(fields.organization));
    setOrganizationType(org.organizationType);
    setOrganization(org.organization);
    setTitle(text(fields.title));
  }, []);

  /** The update to save: an Individual has no organization name or title. */
  const formValues = () => ({
    first_name: firstName.trim(),
    middle_name: middleName.trim(),
    last_name: lastName.trim(),
    organization: organizationType === 'individual' ? 'Individual' : organization.trim(),
    title: organizationType === 'organization' ? title.trim() : '',
  });

  return {
    firstName,
    setFirstName,
    middleName,
    setMiddleName,
    lastName,
    setLastName,
    organization,
    setOrganization,
    organizationType,
    setOrganizationType,
    title,
    setTitle,
    fillForm,
    formValues,
  };
}
