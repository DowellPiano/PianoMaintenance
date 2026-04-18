/**
 * Parses a Django REST Framework error response body into two parts:
 *
 *   fields  — { field_name: "joined error string" }   (show inline next to inputs)
 *   banner  — string for the top-of-modal error bar   (non-field / fallback)
 *
 * DRF error shapes handled:
 *   { field_name: ["msg1", "msg2"] }   — field validation errors
 *   { non_field_errors: ["msg"] }      — cross-field validation
 *   { detail: "msg" }                  — permission / not-found / throttle
 *   { error: "msg" }                   — custom API error key
 */
export function parseApiErrors(data) {
  if (!data || typeof data !== 'object') {
    return { fields: {}, banner: 'An unexpected error occurred.' }
  }

  const NON_FIELD_KEYS = new Set(['non_field_errors', 'detail', 'error'])
  const fields  = {}
  const banners = []

  for (const [key, val] of Object.entries(data)) {
    const msg = Array.isArray(val) ? val.join(' ') : String(val)
    if (NON_FIELD_KEYS.has(key)) {
      banners.push(msg)
    } else {
      fields[key] = msg
    }
  }

  const banner =
    banners.length                ? banners.join(' ')
    : Object.keys(fields).length  ? 'Please fix the errors highlighted below.'
    :                               'Save failed — please try again.'

  return { fields, banner }
}
