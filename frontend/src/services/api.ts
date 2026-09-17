import axios, { AxiosInstance } from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Create axios instance
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000, // 30 seconds
})

// Request interceptor to add auth token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor to handle errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Unauthorized - clear token and redirect to login
      localStorage.removeItem('auth_token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// API service functions
export const authAPI = {
  login: async (phoneNumber: string, password?: string) => {
    const response = await apiClient.post('/api/v1/auth/login', {
      phone_number: phoneNumber,
      password,
    })
    return response.data
  },

  getProfile: async () => {
    const response = await apiClient.get('/api/v1/auth/me')
    return response.data
  },

  getProgress: async () => {
    const response = await apiClient.get('/api/v1/auth/me/progress')
    return response.data
  },
}

export const analyticsAPI = {
  getSummary: async () => {
    const response = await apiClient.get('/api/v1/analytics/summary')
    return response.data
  },

  getDashboard: async () => {
    const response = await apiClient.get('/api/v1/analytics/dashboard')
    return response.data
  },

  getDailyAnalytics: async (date: string) => {
    const response = await apiClient.get(`/api/v1/analytics/daily/${date}`)
    return response.data
  },

  getRangeAnalytics: async (startDate: string, endDate: string) => {
    const response = await apiClient.get('/api/v1/analytics/range', {
      params: { start_date: startDate, end_date: endDate },
    })
    return response.data
  },

  calculateAnalytics: async (targetDate?: string) => {
    const response = await apiClient.post('/api/v1/analytics/calculate', {
      target_date: targetDate,
    })
    return response.data
  },

  getLessons: async (language?: string) => {
    const response = await apiClient.get('/api/v1/analytics/lessons', {
      params: language ? { language } : {},
    })
    return response.data
  },

  getLanguages: async () => {
    const response = await apiClient.get('/api/v1/analytics/languages')
    return response.data
  },

  getEngagement: async () => {
    const response = await apiClient.get('/api/v1/analytics/engagement')
    return response.data
  },

  getReminders: async (days = 30) => {
    const response = await apiClient.get('/api/v1/analytics/reminders', {
      params: { days },
    })
    return response.data
  },

  getQuiz: async (language?: string) => {
    const response = await apiClient.get('/api/v1/analytics/quiz', {
      params: language ? { language } : {},
    })
    return response.data
  },

  getChannels: async () => {
    const response = await apiClient.get('/api/v1/analytics/channels')
    return response.data
  },

  getEmployers: async () => {
    const response = await apiClient.get('/api/v1/analytics/employers')
    return response.data
  },

  getUsers: async () => {
    const response = await apiClient.get('/api/v1/analytics/users')
    return response.data
  },
}

export const certificatesAPI = {
  generate: async (userId?: number) => {
    const response = await apiClient.post('/api/v1/certificates/generate', {
      user_id: userId,
    })
    return response.data
  },

  getMyCertificate: async () => {
    const response = await apiClient.get('/api/v1/certificates/me')
    return response.data
  },

  downloadMyCertificate: async () => {
    const response = await apiClient.get('/api/v1/certificates/me/download', {
      responseType: 'blob',
    })
    return response.data
  },

  verifyCertificate: async (certificateId: string, name: string) => {
    const response = await apiClient.get(`/api/v1/certificates/verify/${certificateId}`, {
      params: { name },
    })
    return response.data
  },
}

export const employersAPI = {
  searchCertificates: async (searchParams: {
    certificate_id?: string
    phone_number?: string
    name?: string
  }) => {
    const response = await apiClient.post('/api/v1/employers/certificates/search', searchParams)
    return response.data
  },
}

// ---------------------------------------------------------------------------
// Learner app (/learn) — separate token + no admin redirect on 401
// ---------------------------------------------------------------------------

export const LEARN_TOKEN_KEY = 'learn_token'

const learnClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
})

learnClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(LEARN_TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export interface LearnButton { id: string; title: string; description: string }
export interface LearnMessage {
  kind: string
  text: string
  buttons: LearnButton[]
  meta: Record<string, unknown>
  role?: 'user' | 'bot'
  timestamp?: string
}
export interface LearnerSummary {
  id: number; name: string; name_confirmed: boolean; language: string
  current_day: number; completed_days: number; preferred_channel: string | null
}
export interface LearnProgress {
  current_day: number; lessons_completed: number; total_lessons: number
  completion_percentage: number; current_day_progress: number; lessons_per_day: number
}
export interface LearnAuth {
  access_token: string; expires_in: number; learner: LearnerSummary; messages: LearnMessage[]; state: string
}
export interface LearnTurn { messages: LearnMessage[]; state: string; learner: LearnerSummary; progress: LearnProgress | null }
export interface LearnState {
  state: string; learner: LearnerSummary; history: LearnMessage[]; progress: LearnProgress | null; push_subscribed: boolean
}
export interface LearnConfig { telegram_link: string | null; vapid_public_key: string | null; pin_min_length: number; ussd_code: string }

export const learnAPI = {
  getConfig: async (): Promise<LearnConfig> => (await learnClient.get('/api/v1/learn/config')).data,

  enrol: async (phone_number: string, pin: string, name?: string): Promise<LearnAuth> =>
    (await learnClient.post('/api/v1/learn/enrol', { phone_number, pin, consent_given: true, name: name || undefined })).data,

  login: async (phone_number: string, pin: string): Promise<LearnAuth> =>
    (await learnClient.post('/api/v1/learn/login', { phone_number, pin })).data,

  getState: async (): Promise<LearnState> => (await learnClient.get('/api/v1/learn/state')).data,

  send: async (payload: { text?: string; interactive_id?: string }): Promise<LearnTurn> =>
    (await learnClient.post('/api/v1/learn/message', payload)).data,

  subscribePush: async (subscription: PushSubscriptionJSON) =>
    learnClient.post('/api/v1/learn/push/subscribe', { subscription, user_agent: navigator.userAgent.slice(0, 255) }),

  unsubscribePush: async (endpoint: string) => learnClient.post('/api/v1/learn/push/unsubscribe', { endpoint }),

  forgetMe: async () => learnClient.post('/api/v1/learn/forget-me'),
}

export default apiClient
