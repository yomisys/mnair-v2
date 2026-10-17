import axios, { AxiosInstance } from 'axios'

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

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

// White-label sponsor branding (public landing page /s/<code>, /learn, portal)
export interface SponsorAdvert {
  headline: string; body: string | null; cta_label: string | null; cta_url: string | null; image_url: string | null
}
export interface SponsorBrandBase {
  sponsor_name: string; tagline: string | null; welcome_message: string | null; brand_color: string | null
  website_url: string | null; logo_url: string | null; advert: SponsorAdvert | null
}
export interface SponsorBrand extends SponsorBrandBase { code: string; join_url: string; telegram_url: string | null }
export interface SponsorBranding {
  brand_color: string | null; tagline: string | null; welcome_message: string | null; website_url: string | null
  ad_enabled: boolean; ad_headline: string | null; ad_body: string | null; ad_cta_label: string | null; ad_cta_url: string | null
  logo_url: string | null; ad_image_url: string | null; ad_suspended: boolean; ad_live: boolean
}
export type BrandingEdit = Partial<Omit<SponsorBranding, 'logo_url' | 'ad_image_url' | 'ad_suspended' | 'ad_live'>>

/** Brand image paths come back relative to the API. */
export const assetUrl = (path: string | null): string | null => (path ? `${API_BASE_URL}${path}` : null)

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

  brand: async (code: string): Promise<SponsorBrand> =>
    (await learnClient.get(`/api/v1/sponsors/brand/${encodeURIComponent(code)}`)).data,

  mySponsor: async (): Promise<{ sponsor: SponsorBrandBase | null }> => (await learnClient.get('/api/v1/learn/sponsor')).data,

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
  branding: SponsorBranding
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
  certificatePdf: async (certificateId: string): Promise<Blob> =>
    (await sponsorClient.get(`/api/v1/sponsors/me/certificates/${encodeURIComponent(certificateId)}/pdf`, { responseType: 'blob' })).data,
  certificateLink: async (certificateId: string, days = 7): Promise<ShareLink> =>
    withFullUrl((await sponsorClient.post(`/api/v1/sponsors/me/certificates/${encodeURIComponent(certificateId)}/link`, { days })).data),
  branding: async (): Promise<SponsorBranding> => (await sponsorClient.get('/api/v1/sponsors/me/branding')).data,
  updateBranding: async (body: BrandingEdit): Promise<SponsorBranding> =>
    (await sponsorClient.patch('/api/v1/sponsors/me/branding', body)).data,
  uploadBrandImage: async (kind: 'logo' | 'ad_image', file: File): Promise<SponsorBranding> => {
    const data = new FormData()
    data.append('file', file)
    return (await sponsorClient.post(`/api/v1/sponsors/me/branding/${kind}`, data, { headers: { 'Content-Type': 'multipart/form-data' } })).data
  },
  removeAdImage: async (): Promise<SponsorBranding> => (await sponsorClient.delete('/api/v1/sponsors/me/branding/ad_image')).data,
}

// ---------------------------------------------------------------------------
// Admin back office
// ---------------------------------------------------------------------------

export interface ShareLink { certificate_id: string; path: string; expires_at: string; url: string }

const withFullUrl = (r: Omit<ShareLink, 'url'>): ShareLink => ({ ...r, url: `${API_BASE_URL}${r.path}` })

export const saveBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export interface Paged<T> { total: number; offset: number; limit: number; items: T[] }

export interface AdminOverview {
  learners: {
    total: number; active_last_7_days: number; new_last_7_days: number; inactive_accounts: number
    sponsored: number; completed_course: number; certificates_issued: number
  }
  sponsors: { total: number; active: number; owing: number }
  revenue: {
    charged_kobo: number; sponsor_collected_kobo: number; learner_certificate_collected_kobo: number
    total_collected_kobo: number; outstanding_kobo: number; sponsor_credit_kobo: number
    deposits_outstanding_kobo: number; collected_last_30_days_kobo: number; pending_payments: number
  }
  trend: { month: string; charged_kobo: number; collected_kobo: number; certificates: number }[]
}

export interface AdminLearnerRow {
  id: number; name: string; name_confirmed: boolean; phone_number: string; email: string | null
  role: string; language: string; current_day: number; completed_days: number; is_active: boolean
  preferred_channel: string | null; sponsor: { id: number; name: string; code: string } | null
  certificate_id: string | null; certificate_access: string | null
  created_at: string | null; last_active_at: string | null
}

export interface AdminCertificate {
  certificate_id: string; learner_name: string; language: string; access_type: string; is_verified: boolean
  sponsor_name: string | null; organization_id: number | null; average_quiz_score: number | null
  days_to_complete: number | null; issued_at: string | null; user_id?: number
}

export interface AdminPayment {
  reference: string; purpose: string; status: string; amount_kobo: number
  organization_id: number | null; organization_name: string | null; user_id: number | null; user_name: string | null
  email: string; channel: string | null; note: string | null; gateway_response: string | null
  paid_at: string | null; created_at: string | null
}

export interface AuditEntry {
  id: number; admin_user_id: number | null; admin: string; action: string; target_type: string | null
  target_id: string | null; summary: string; details: Record<string, unknown> | null; ip_address: string | null
  created_at: string | null
}

export interface AdminLearnerDetail extends Omit<AdminLearnerRow, 'sponsor' | 'certificate_id' | 'certificate_access'> {
  has_pin: boolean; has_password: boolean; telegram_linked: boolean; network_operator: string | null
  consent_given: boolean; consent_date: string | null
  sponsor: { id: number; name: string; code: string; sponsored_at: string | null } | null
  progress: { lessons_completed: number; quiz_attempts: number; quiz_correct: number; quiz_questions: number; quiz_accuracy: number | null }
  certificates: AdminCertificate[]
  payments: AdminPayment[]
  history: AuditEntry[]
}

type Params = Record<string, string | number | boolean | undefined | null>
const clean = (p: Params) => Object.fromEntries(Object.entries(p).filter(([, v]) => v !== undefined && v !== null && v !== ''))

export const adminAPI = {
  overview: async (): Promise<AdminOverview> => (await apiClient.get('/api/v1/admin/overview')).data,

  learners: async (p: Params): Promise<Paged<AdminLearnerRow>> =>
    (await apiClient.get('/api/v1/admin/learners', { params: clean(p) })).data,
  learner: async (id: number): Promise<AdminLearnerDetail> => (await apiClient.get(`/api/v1/admin/learners/${id}`)).data,
  updateLearner: async (id: number, body: Record<string, unknown>) =>
    (await apiClient.patch(`/api/v1/admin/learners/${id}`, body)).data,
  resetPin: async (id: number) => (await apiClient.post(`/api/v1/admin/learners/${id}/reset-pin`)).data,
  removeSponsor: async (id: number) => (await apiClient.post(`/api/v1/admin/learners/${id}/remove-sponsor`)).data,

  certificates: async (p: Params): Promise<Paged<AdminCertificate>> =>
    (await apiClient.get('/api/v1/admin/certificates', { params: clean(p) })).data,
  certificatePdf: async (certificateId: string): Promise<Blob> =>
    (await apiClient.get(`/api/v1/admin/certificates/${encodeURIComponent(certificateId)}/pdf`, { responseType: 'blob', timeout: 60000 })).data,
  certificateLink: async (certificateId: string, days = 7, allowUnpaid = false): Promise<ShareLink> =>
    withFullUrl((await apiClient.post(`/api/v1/admin/certificates/${encodeURIComponent(certificateId)}/link`, { days, allow_unpaid: allowUnpaid })).data),

  payments: async (p: Params): Promise<Paged<AdminPayment> & { totals_kobo: Record<string, number> }> =>
    (await apiClient.get('/api/v1/admin/payments', { params: clean(p) })).data,
  voidPayment: async (reference: string, reason: string) =>
    (await apiClient.post(`/api/v1/admin/payments/${encodeURIComponent(reference)}/void`, { reason })).data,

  audit: async (p: Params): Promise<Paged<AuditEntry> & { actions: string[] }> =>
    (await apiClient.get('/api/v1/admin/audit', { params: clean(p) })).data,

  // sponsors
  sponsors: async () => (await apiClient.get('/api/v1/admin/sponsors')).data,
  sponsor: async (id: number) => (await apiClient.get(`/api/v1/admin/sponsors/${id}`)).data,
  createSponsor: async (body: Record<string, unknown>) => (await apiClient.post('/api/v1/admin/sponsors', body)).data,
  updateSponsor: async (id: number, body: Record<string, unknown>) => (await apiClient.patch(`/api/v1/admin/sponsors/${id}`, body)).data,
  sponsorLearners: async (id: number, offset = 0, limit = 25) =>
    (await apiClient.get(`/api/v1/admin/sponsors/${id}/learners`, { params: { offset, limit } })).data,
  sponsorLearnersCsv: async (id: number): Promise<Blob> =>
    (await apiClient.get(`/api/v1/admin/sponsors/${id}/learners.csv`, { responseType: 'blob' })).data,
  sponsorPayments: async (id: number): Promise<AdminPayment[]> => (await apiClient.get(`/api/v1/admin/sponsors/${id}/payments`)).data,
  sponsorStatement: async (id: number, year: number, month: number): Promise<SponsorStatement> =>
    (await apiClient.get(`/api/v1/admin/sponsors/${id}/statement`, { params: { year, month } })).data,
  createCode: async (id: number, body: Record<string, unknown>) => (await apiClient.post(`/api/v1/admin/sponsors/${id}/codes`, body)).data,
  updateCode: async (codeId: number, body: Record<string, unknown>) => (await apiClient.patch(`/api/v1/admin/sponsors/codes/${codeId}`, body)).data,
  uploadLogo: async (id: number, file: File) => {
    const data = new FormData()
    data.append('file', file)
    return (await apiClient.post(`/api/v1/admin/sponsors/${id}/logo`, data, { headers: { 'Content-Type': 'multipart/form-data' } })).data
  },
  paymentLink: async (id: number, purpose: 'deposit' | 'balance', amountKobo?: number) =>
    (await apiClient.post(`/api/v1/admin/sponsors/${id}/payment-link`, { purpose, amount_kobo: amountKobo })).data,
  manualPayment: async (id: number, amountKobo: number, note: string, paidAt?: string) =>
    (await apiClient.post(`/api/v1/admin/sponsors/${id}/manual-payment`, { amount_kobo: amountKobo, note, paid_at: paidAt || undefined })).data,
}

export const formatNaira = (kobo: number): string =>
  `₦${(kobo / 100).toLocaleString('en-NG', { maximumFractionDigits: kobo % 100 ? 2 : 0 })}`

export default apiClient

