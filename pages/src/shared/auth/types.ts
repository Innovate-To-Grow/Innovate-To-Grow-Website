export interface User {
  member_uuid: string;
  email: string;
  profile_image?: string;
  is_staff?: boolean;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface LoginResponse {
  message: string;
  access: string;
  refresh: string;
  user: User;
  redirect_to?: string;
}

export interface EmailAuthRequestResponse {
  message: string;
}

export interface EmailAuthVerifyResponse extends LoginResponse {
  next_step: 'account' | 'complete_profile';
  requires_profile_completion: boolean;
}

export interface RegisterResponse {
  message: string;
  next_step: string;
}

export interface MessageResponse {
  message: string;
}

export interface VerificationTokenResponse {
  message: string;
  verification_token: string;
}

export interface AccountEmailsResponse {
  emails: string[];
}

export interface ProfileResponse {
  member_uuid: string;
  email: string;
  email_verified: boolean;
  primary_email_id: string | null;
  first_name: string;
  middle_name: string;
  last_name: string;
  organization: string;
  title: string;
  email_subscribe: boolean;
  is_staff: boolean;
  is_active: boolean;
  date_joined: string;
  profile_image?: string;
}

export interface ContactEmail {
  id: string;
  email_address: string;
  email_type: 'primary' | 'secondary' | 'other';
  subscribe: boolean;
  verified: boolean;
  created_at: string;
}

export interface ContactPhone {
  id: string;
  phone_number: string;
  region: string;
  region_display: string;
  subscribe: boolean;
  verified: boolean;
  created_at: string;
}
