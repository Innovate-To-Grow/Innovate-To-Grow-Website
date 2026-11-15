export {
  authApi,
  API_BASE_URL,
  isDefinitiveAuthFailure,
} from './session/client';
export { getContactPhones, createContactPhone, updateContactPhone, deleteContactPhone, requestContactPhoneVerification, verifyContactPhoneCode, getContactEmails, createContactEmail, updateContactEmail, deleteContactEmail, requestContactEmailVerification, verifyContactEmailCode, makeContactEmailPrimary } from './account/contacts';
export { register, login, requestLoginCode, requestEmailAuthCode, verifyLoginCode, verifyEmailAuthCode, requestPhoneAuthCode, verifyPhoneAuthCode, verifyRegistrationCode, resendRegistrationCode, requestPasswordReset, verifyPasswordResetCode, confirmPasswordReset, requestPasswordChangeCode, verifyPasswordChangeCode, confirmPasswordChange, requestAccountDeletionCode, verifyAccountDeletionCode, confirmAccountDeletion } from './signin/flows';
export { SessionNotSavedError, MalformedLoginResponseError } from './contracts/errors';
export { classifyLoginLinkFailure } from './navigation/loginLinkFailure';
export type { LoginLinkFailure, LoginLinkFailureKind } from './navigation/loginLinkFailure';
export { hasRequiredNameFields } from './account/profileCompletion';
export { getProfile, updateProfileFields, uploadProfileImage, getAccountEmails } from './account/profile';
export { getSafeInternalRedirectPath, buildCompleteProfilePath, buildLoginPath, getPostAuthPath, getEmailAuthSourcePath } from './navigation/redirects';
export { loginLinkAutoLogin, impersonateAutoLogin, logout, isAuthenticated, bootstrapAuthSession, openSmsLink, getRegisterLinkPath } from './signin/session';
export type { SmsLinkResult } from './signin/session';
export { isProfileCompletionRequired, setProfileCompletionRequired, clearProfileCompletionRequired, getAccessToken, getRefreshToken, getStoredUser, getStoredSession, isCurrentSession, setTokens, persistAuthSession, updateSessionTokens, updateStoredUser, updateStoredSessionProfile, clearTokens } from './session/storage';
export type {StoredAuthSession, SessionGuard} from './session/storage';
export type { User, AuthTokens, AuthNextStep, EmailAuthSource, EmailAuthFlow, PhoneAuthSource, LoginResponse, EmailAuthRequestResponse, PhoneAuthRequestResponse, SmsChallengeResponse, EmailAuthVerifyResponse, RegisterResponse, MessageResponse, VerificationTokenResponse, PasswordChangeRequestResponse, AccountEmailsResponse, ProfileResponse, ContactEmail, ContactPhone } from './contracts/types';
