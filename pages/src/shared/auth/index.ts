export { authApi, API_BASE_URL } from './client';
export { getContactPhones, createContactPhone, updateContactPhone, deleteContactPhone, requestContactPhoneVerification, verifyContactPhoneCode, getContactEmails, createContactEmail, updateContactEmail, deleteContactEmail, requestContactEmailVerification, verifyContactEmailCode, makeContactEmailPrimary } from './contacts';
export { register, login, requestLoginCode, requestEmailAuthCode, verifyLoginCode, verifyEmailAuthCode, verifyRegistrationCode, consumeEmailAuthQuery, resendRegistrationCode, requestPasswordReset, verifyPasswordResetCode, confirmPasswordReset, requestPasswordChangeCode, verifyPasswordChangeCode, confirmPasswordChange, requestAccountDeletionCode, verifyAccountDeletionCode, confirmAccountDeletion, subscribe } from './flows';
export { hasRequiredNameFields } from './profileCompletion';
export { getProfile, updateProfileFields, uploadProfileImage, getAccountEmails } from './profile';
export { getSafeInternalRedirectPath, buildCompleteProfilePath, getPostAuthPath, getEmailAuthSourcePath } from './redirects';
export { ticketAutoLogin, magicAutoLogin, unsubscribeAutoLogin, impersonateAutoLogin, logout, isAuthenticated } from './session';
export { isProfileCompletionRequired, setProfileCompletionRequired, clearProfileCompletionRequired, getAccessToken, getRefreshToken, getStoredUser, setTokens, persistAuthSession, updateStoredUser, clearTokens } from './storage';
export type { User, AuthTokens, AuthNextStep, EmailAuthSource, EmailAuthFlow, LoginResponse, EmailAuthRequestResponse, EmailAuthVerifyResponse, RegisterResponse, MessageResponse, VerificationTokenResponse, AccountEmailsResponse, ProfileResponse, ContactEmail, ContactPhone } from './types';
