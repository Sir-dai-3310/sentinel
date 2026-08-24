import axios from 'axios'
import type { AxiosError, InternalAxiosRequestConfig } from 'axios'

export const TOKEN_STORAGE_KEY = 'sentinel_token'

function tokenStorage(): Storage | null {
  return typeof localStorage !== 'undefined' && typeof localStorage.getItem === 'function'
    ? localStorage
    : null
}

/**
 * Same-origin relative base path. In dev the Vite proxy forwards /api -> :8000;
 * in production nginx does the same. This removes the 8 hardcoded
 * `http://localhost:8000` literals (which pointed at the *user's* machine in
 * production) and the mixed-content `ws://` failure mode.
 */
export const api = axios.create({
  baseURL: '',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      tokenStorage()?.removeItem(TOKEN_STORAGE_KEY)
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_STORAGE_KEY, token)
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY)
}

export function wsUrl(path: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const token = getToken()
  const suffix = token ? `?token=${encodeURIComponent(token)}` : ''
  return `${proto}//${window.location.host}${path}${suffix}`
}

/** Login against POST /api/v1/auth/login and persist the returned JWT. */
export async function login(username: string, password: string): Promise<void> {
  const resp = await axios.post('/api/v1/auth/login', { username, password })
  setToken(resp.data.access_token)
}
