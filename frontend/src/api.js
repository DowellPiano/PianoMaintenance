/**
 * Authenticated fetch wrapper.
 *
 * - Reads the stored token from localStorage and injects the
 *   `Authorization: Token <key>` header on every request.
 * - On a 401 response, clears stored credentials and redirects to /login
 *   so the user is never left in a broken half-authed state.
 * - Does NOT touch Content-Type — callers set it themselves (or omit it
 *   for multipart/FormData so the browser sets the boundary automatically).
 */
export function apiFetch(path, opts = {}) {
  const token = localStorage.getItem('authToken')
  const headers = { ...(opts.headers ?? {}) }
  if (token) headers['Authorization'] = `Token ${token}`

  return fetch(path, { ...opts, headers }).then(res => {
    if (res.status === 401) {
      localStorage.removeItem('authToken')
      localStorage.removeItem('authUser')
      window.location.href = '/login'
      // Throw so callers' .catch() handlers run instead of .then(r => r.json())
      throw new Error('Session expired. Please log in again.')
    }
    return res
  })
}
