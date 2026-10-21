import type {ChangeEvent, FormEvent} from 'react';
import type {OrganizationType} from '../../../shared/useProfileForm';

export type {OrganizationType};

export interface ProfileSectionProps {
  firstName: string;
  middleName: string;
  lastName: string;
  organizationType: OrganizationType;
  organization: string;
  title: string;
  profileImage: string | null;
  imageUploading: boolean;
  imageError: string | null;
  profileSaving: boolean;
  profileMessage: string | null;
  profileError: string | null;
  isEditingProfile: boolean;
  onImageChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onSubmit: (event: FormEvent) => void;
  onFirstNameChange: (value: string) => void;
  onMiddleNameChange: (value: string) => void;
  onLastNameChange: (value: string) => void;
  onOrganizationTypeChange: (value: OrganizationType) => void;
  onOrganizationChange: (value: string) => void;
  onTitleChange: (value: string) => void;
  onRetryProfile: () => void;
  onStartEditing: () => void;
  onCancelEditing: () => void;
}
