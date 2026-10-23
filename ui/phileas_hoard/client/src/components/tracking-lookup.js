export const initialLookup = { fields: { tracking_number: "", carrier: "" }, request: null, result: null, error: null, loading: false };

export function trackingLookup(state, action) {
  if (action.type === "change") return { ...state, fields: { ...state.fields, [action.field]: action.value }, request: null, result: null, error: null, loading: false };
  if (action.type === "start") return { ...state, request: action.id, result: null, error: null, loading: true };
  if (action.id !== state.request) return state;
  if (action.type === "resolved") return { ...state, loading: false, result: { query: action.query, data: action.data } };
  if (action.type === "failed") return { ...state, loading: false, error: action.error };
  return state;
}
