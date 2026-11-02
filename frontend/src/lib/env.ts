const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL

if (configuredBaseUrl === undefined || configuredBaseUrl === null) {
  throw new Error('VITE_API_BASE_URL is required')
}

// Same-origin container builds set VITE_API_BASE_URL=/ so fetches stay relative.
export const apiBaseUrl = configuredBaseUrl === '/' ? '' : configuredBaseUrl.replace(/\/$/, '')
