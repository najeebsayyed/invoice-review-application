const configuredBaseUrl =
  import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '')

// Same-origin container builds or empty baseUrl set VITE_API_BASE_URL=/ so fetches stay relative.
export const apiBaseUrl =
  !configuredBaseUrl || configuredBaseUrl === '/' ? '' : configuredBaseUrl.replace(/\/$/, '')
