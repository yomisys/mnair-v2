import axios, { AxiosInstance, AxiosRequestConfig } from 'axios'

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

  verifyCertificate: async (certificateId: string) => {
    const response = await apiClient.get(`/api/v1/certificates/verify/${certificateId}`)
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

export default apiClient
