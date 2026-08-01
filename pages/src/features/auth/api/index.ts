export {
  authApi,
  API_BASE_URL,
  isDefinitiveAuthFailure,
} from './client';
export { getContactPhones, createContactPhone, updateContactPhone, deleteContactPhone, requestContactPhoneVerification, verifyContactPhoneCode, getContactEmails, createContactEmail, updateContactEmail, deleteContactEmail, requestContactEmailVerification, verifyContactEmailCode, makeContactEmailPrimary } from './contacts';
export { register, login, requestLoginCode, requestEmailAuthCode, verifyLoginCode, verifyEmailAuthCode, requestPhoneAuthCode, verifyPhoneAuthCode, verifyRegistrationCode, resendRegistrationCode, requestPasswordReset, verifyPasswordResetCode, confirmPasswordReset, requestPasswordChangeCode, verifyPasswordChangeCode, confirmPasswordChange, requestAccountDeletionCode, verifyAccountDeletionCode, confirmAccountDeletion, subscribe } from './flows';
export { hasRequiredNameFields } from './profileCompletion';
export { getProfile, updateProfileFields, uploadProfileImage, getAccountEmails } from './profile';
export { getSafeInternalRedirectPath, buildCompleteProfilePath, getPostAuthPath, getEmailAuthSourcePath } from './redirects';
export { loginLinkAutoLogin, unsubscribeAutoLogin, impersonateAutoLogin, logout, isAuthenticated, bootstrapAuthSession } from './session';
export { isProfileCompletionRequired, setProfileCompletionRequired, clearProfileCompletionRequired, getAccessToken, getRefreshToken, getStoredUser, getStoredSession, isCurrentSession, setTokens, persistAuthSession, updateSessionTokens, updateStoredUser, updateStoredSessionProfile, clearTokens } from './storage';
export type {StoredAuthSession, SessionGuard} from './storage';
export type { User, AuthTokens, AuthNextStep, EmailAuthSource, EmailAuthFlow, PhoneAuthSource, LoginResponse, EmailAuthRequestResponse, PhoneAuthRequestResponse, SmsChallengeResponse, EmailAuthVerifyResponse, RegisterResponse, MessageResponse, VerificationTokenResponse, PasswordChangeRequestResponse, AccountEmailsResponse, ProfileResponse, ContactEmail, ContactPhone } from './types';
