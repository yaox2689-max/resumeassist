/**
 * API service layer
 * GitHub analysis uses real backend; other endpoints use mock adapter.
 */

import { mockAdapter } from './mock.js'
import { useAuth } from '@/stores/auth.js'

function getAuthHeaders() {
  const { getToken } = useAuth()
  const token = getToken()
  if (token) {
    return { 'Authorization': `Bearer ${token}` }
  }
  return {}
}

// Mock adapter for non-GitHub endpoints
async function mockRequest(path, options = {}) {
  await new Promise((r) => setTimeout(r, 2000))
  return mockAdapter(path, options)
}

// Real API call to FastAPI backend
async function realRequest(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
    ...options.headers,
  }
  const res = await fetch(`/api${path}`, {
    ...options,
    headers,
  })
  if (res.status === 401) {
    // Token expired or invalid — clear auth
    const { logout } = useAuth()
    logout()
    window.location.href = '/login'
    throw new Error('登录已过期，请重新登录')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail = body?.detail || `API error: ${res.status}`
    throw new Error(detail)
  }
  // Handle 204 No Content (e.g. DELETE responses)
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  // Auth
  register(username, password) {
    return realRequest('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  },

  login(username, password) {
    return realRequest('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  },

  getMe() {
    return realRequest('/auth/me')
  },

  // GitHub analysis (real backend)
  analyzeGithub(url) {
    return realRequest('/analysis', {
      method: 'POST',
      body: JSON.stringify({ repo_url: url }),
    })
  },

  getGithubRepos() {
    return realRequest('/analysis')
  },

  getGithubRepo(id) {
    return realRequest(`/analysis/${id}`)
  },

  getGithubDeep(id) {
    return realRequest(`/analysis/${id}`)
  },

  // Task progress (real backend)
  getTaskStatus(taskId) {
    return realRequest(`/tasks/${taskId}`)
  },

  getTaskStreamUrl(taskId) {
    return `/api/tasks/${taskId}/stream`
  },

  // JD analysis (real backend)
  analyzeJd(text) {
    return realRequest('/jd/analyze', {
      method: 'POST',
      body: JSON.stringify({ text }),
    })
  },

  // Resume CRUD (real backend)
  getResumes(userId) {
    const params = userId ? `?user_id=${encodeURIComponent(userId)}` : ''
    return realRequest(`/resumes${params}`)
  },

  getResume(resumeId) {
    return realRequest(`/resumes/${resumeId}`)
  },

  async uploadResume(file, userId) {
    const formData = new FormData()
    formData.append('file', file)
    if (userId) formData.append('user_id', userId)
    const { getToken } = useAuth()
    const token = getToken()
    const headers = token ? { 'Authorization': `Bearer ${token}` } : {}
    const res = await fetch('/api/resumes/upload', {
      method: 'POST',
      body: formData,
      headers,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `Upload failed: ${res.status}` }))
      throw new Error(err.detail || `Upload failed: ${res.status}`)
    }
    return res.json()
  },

  deleteResume(resumeId) {
    return realRequest(`/resumes/${resumeId}`, { method: 'DELETE' })
  },

  analyzeResume(resumeId, force = false) {
    return realRequest(`/resumes/${resumeId}/analyze?force=${force}`, {
      method: 'POST',
    })
  },

  // Interview sessions (real backend)
  createSession({ profileId, mode = 'text', resumeId = null, githubRepoIds = [] }) {
    return realRequest('/sessions', {
      method: 'POST',
      body: JSON.stringify({
        profile_id: profileId,
        mode,
        resume_id: resumeId,
        github_repo_ids: githubRepoIds,
      }),
    })
  },

  getSessions({ userId = null, status = null, profileId = null } = {}) {
    const params = new URLSearchParams()
    if (userId) params.set('user_id', userId)
    if (status) params.set('status', status)
    if (profileId) params.set('profile_id', profileId)
    const qs = params.toString()
    return realRequest(`/sessions${qs ? `?${qs}` : ''}`)
  },

  getSession(sessionId) {
    return realRequest(`/sessions/${sessionId}`)
  },

  getSessionEvents(sessionId) {
    return realRequest(`/sessions/${sessionId}/events`)
  },

  sendSSEMessage(sessionId, text) {
    return realRequest(`/sessions/${sessionId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    })
  },

  streamEvents(sessionId) {
    return new EventSource(`/api/sessions/${sessionId}/stream`)
  },

  finalizeSession(sessionId) {
    return realRequest(`/sessions/${sessionId}/finalize`, {
      method: 'POST',
    })
  },

  deleteSession(sessionId) {
    return realRequest(`/sessions/${sessionId}`, { method: 'DELETE' })
  },

  getVoiceWebSocketUrl(sessionId, { profileId, userId, mode = 'voice' } = {}) {
    const params = new URLSearchParams({
      profile: profileId,
      mode,
    })
    if (userId) params.set('user_id', userId)
    const { getToken } = useAuth()
    const token = getToken()
    if (token) params.set('token', token)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}/ws/voice/${sessionId}?${params.toString()}`
  },
}
