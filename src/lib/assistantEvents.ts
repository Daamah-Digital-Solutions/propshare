// Any page can open the PropShare AI panel (the Support page's "Ask PropShare AI" does).
export const OPEN_ASSISTANT_EVENT = "capimax:open-assistant";

/** Opens the assistant's chat panel. False when no assistant is on the page to answer. */
export function openAssistant(): boolean {
  const event = new Event(OPEN_ASSISTANT_EVENT, { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}
