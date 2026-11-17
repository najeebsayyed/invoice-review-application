const defaultProdApiUrl = 'https://invoice-review-api.greenmushroom-2b5a71a4.centralindia.azurecontainerapps.io'

const configuredBaseUrl =
  import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : defaultProdApiUrl)

// Same-origin container builds or empty baseUrl set VITE_API_BASE_URL=/ so fetches stay relative.
export const apiBaseUrl =
  !configuredBaseUrl || configuredBaseUrl === '/' ? '' : configuredBaseUrl.replace(/\/$/, '')

