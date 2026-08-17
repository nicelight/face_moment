export const DISPLAY_CLIENT_TOKEN_STORAGE_KEY = "face-moment.display-client-token";

function storage() {
  if (!globalThis.localStorage) {
    throw new Error("display_client_profile_unavailable");
  }
  return globalThis.localStorage;
}

function normalizeToken(value) {
  if (typeof value !== "string") throw new TypeError("display_client_token_required");
  const token = value.trim();
  if (!token || /[\u0000-\u001f\u007f]/u.test(token)) {
    throw new TypeError("display_client_token_invalid");
  }
  return token;
}

export function readDisplayClientToken() {
  return storage().getItem(DISPLAY_CLIENT_TOKEN_STORAGE_KEY);
}

export function saveDisplayClientToken(value) {
  const token = normalizeToken(value);
  storage().setItem(DISPLAY_CLIENT_TOKEN_STORAGE_KEY, token);
  return token;
}

export function clearDisplayClientToken() {
  storage().removeItem(DISPLAY_CLIENT_TOKEN_STORAGE_KEY);
}

export function getDisplayAuthorization() {
  const token = readDisplayClientToken();
  return token ? `Bearer ${token}` : null;
}

export function getDisplayRequestHeaders(headers = {}) {
  const authorization = getDisplayAuthorization();
  return authorization ? { ...headers, Authorization: authorization } : { ...headers };
}
