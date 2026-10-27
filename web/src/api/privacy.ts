export const AUTH_LOST = "opspilot:auth-lost";
export function clearPrivateState() {
  sessionStorage.clear();
  window.dispatchEvent(new Event(AUTH_LOST));
}
