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

  enrol: async (phone_number: string, pin: string, name?: string, sponsor_code?: string): Promise<LearnAuth> =>
    (await learnClient.post('/api/v1/learn/enrol', {
      phone_number, pin, consent_given: true, name: name || undefined, sponsor_code: sponsor_code || undefined,
    })).data,

  lookupSponsor: async (code: string): Promise<{ code: string; sponsor_name: string }> =>
    (await learnClient.get(`/api/v1/sponsors/code/${encodeURIComponent(code)}`)).data,

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

// ---------------------------------------------------------------------------
// Payments (public status check for the /payment/callback page)
// ---------------------------------------------------------------------------

export interface PaymentStatus { reference: string; status: string; purpose: string; amount_kobo: number }

export const paymentsAPI = {
  verify: async (reference: string): Promise<PaymentStatus> =>
    (await learnClient.get(`/api/v1/payments/verify/${encodeURIComponent(reference)}`)).data,
}

// ---------------------------------------------------------------------------
// Sponsor portal (/sponsor) — its own token; a sponsor is never an admin
// ---------------------------------------------------------------------------

export const SPONSOR_TOKEN_KEY = 'sponsor_token'

const sponsorClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
})

sponsorClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(SPONSOR_TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export interface SponsorAccount {
  certificates_billed: number; charged_kobo: number; paid_kobo: number; deposit_paid_kobo: number
  deposit_outstanding_kobo: number; credit_remaining_kobo: number; amount_due_kobo: number
}
export interface SponsorCodeSummary {
  code: string; label: string | null; max_enrolments: number | null; is_active: boolean; enrolled: number
  join_url: string; telegram_url: string | null
}
export interface SponsorDashboard {
  organization: {
    id: number; name: string; package: string; price_per_certificate_kobo: number
    deposit_kobo: number; learner_cap: number | null; has_logo: boolean
  }
  learners: {
    enrolled: number; active_last_7_days: number; certified: number; completion_rate: number
    average_quiz_score: number | null; days_completed: Record<string, number>; by_language: Record<string, number>
  }
  codes: SponsorCodeSummary[]
  account: SponsorAccount
  payments_enabled: boolean
}
export interface SponsorLearner {
  name: string; language: string; current_day: number; completed_days: number; certified: boolean
  certificate_id: string | null; joined_at: string | null; last_active_at: string | null
}
export interface SponsorStatement {
  organization: string; period: string; price_per_certificate_kobo: number
  opening_balance_kobo: number; certificates_issued: number; charges_kobo: number; payments_kobo: number
  closing_balance_kobo: number; amount_due_kobo: number
  charges: { certificate_id: string; amount_kobo: number; issued_at: string }[]
  payments: { reference: string; purpose: string; amount_kobo: number; channel: string | null; paid_at: string }[]
}

export const sponsorAPI = {
  login: async (email: string, password: string): Promise<{ access_token: string; organization: { id: number; name: string } }> =>
    (await sponsorClient.post('/api/v1/sponsors/login', { email, password })).data,
  dashboard: async (): Promise<SponsorDashboard> => (await sponsorClient.get('/api/v1/sponsors/me/dashboard')).data,
  learners: async (offset = 0, limit = 50): Promise<{ total: number; items: SponsorLearner[] }> =>
    (await sponsorClient.get('/api/v1/sponsors/me/learners', { params: { offset, limit } })).data,
  learnersCsv: async (): Promise<Blob> =>
    (await sponsorClient.get('/api/v1/sponsors/me/learners.csv', { responseType: 'blob' })).data,
  statement: async (year: number, month: number): Promise<SponsorStatement> =>
    (await sponsorClient.get('/api/v1/sponsors/me/statement', { params: { year, month } })).data,
  pay: async (purpose: 'deposit' | 'balance'): Promise<{ authorization_url: string; amount_kobo: number }> =>
    (await sponsorClient.post('/api/v1/sponsors/me/pay', { purpose })).data,
}

export const formatNaira = (kobo: number): string =>
  `₦${(kobo / 100).toLocaleString('en-NG', { maximumFractionDigits: kobo % 100 ? 2 : 0 })}`

export default apiClient

