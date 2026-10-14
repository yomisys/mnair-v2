import React from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import {
  Box,
  AppBar,
  Toolbar,
  Typography,
  Button,
  Container,
  Stack,
} from '@mui/material'
import { VerifiedUser as VerifyIcon, School as LearnIcon } from '@mui/icons-material'
import { useAuth } from './contexts/AuthContext'
import Home from './pages/Home'
import Learn from './pages/Learn'
import VerifyCertificate from './pages/VerifyCertificate'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import LessonsReport from './pages/LessonsReport'
import LanguageReport from './pages/LanguageReport'
import EngagementReport from './pages/EngagementReport'
import QuizReport from './pages/QuizReport'
import ChannelsReport from './pages/ChannelsReport'
import EmployersReport from './pages/EmployersReport'
import UsersReport from './pages/UsersReport'
import SponsorsAdmin from './pages/SponsorsAdmin'
import SponsorDetail from './pages/SponsorDetail'
import LearnersAdmin from './pages/LearnersAdmin'
import LearnerDetail from './pages/LearnerDetail'
import CertificatesAdmin from './pages/CertificatesAdmin'
import PaymentsAdmin from './pages/PaymentsAdmin'
import AuditLog from './pages/AuditLog'
import SponsorPortal from './pages/SponsorPortal'
import PaymentCallback from './pages/PaymentCallback'
import AdminLayout from './components/AdminLayout'

const ProtectedRoute: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return <div>Loading...</div>
  }

  return isAuthenticated ? children : <Navigate to="/login" />
}

const PublicNavBar: React.FC = () => {
  const location = useLocation()

  return (
    <AppBar position="static" elevation={1}>
      <Toolbar>
        <Typography variant="h6" component="div" sx={{ flexGrow: 1, fontWeight: 'bold' }}>
          MNAIR
        </Typography>
        <Stack direction="row" spacing={2}>
          {location.pathname !== '/' && (
            <Button color="inherit" href="/">
              Home
            </Button>
          )}
          {location.pathname !== '/learn' && (
            <Button color="inherit" href="/learn" startIcon={<LearnIcon />}>
              Learn
            </Button>
          )}
          {location.pathname !== '/verify' && (
            <Button color="inherit" href="/verify" startIcon={<VerifyIcon />}>
              Verify Certificate
            </Button>
          )}
          <Button color="inherit" href="/login">
            Admin Login
          </Button>
        </Stack>
      </Toolbar>
    </AppBar>
  )
}

const PublicFooter: React.FC = () => (
  <Box
    component="footer"
    sx={{
      py: 3,
      px: 2,
      mt: 'auto',
      backgroundColor: 'primary.main',
      color: 'white',
    }}
  >
    <Container maxWidth="lg">
      <Stack spacing={2}>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={2}
          justifyContent="space-between"
          alignItems={{ xs: 'center', md: 'flex-start' }}
        >
          <Box sx={{ textAlign: { xs: 'center', md: 'left' } }}>
            <Typography variant="h6" gutterBottom fontWeight="bold">
              Make Nigeria AI Ready
            </Typography>
            <Typography variant="body2" sx={{ opacity: 0.9 }}>
              Empowering Nigerians with AI literacy
            </Typography>
          </Box>

          <Stack spacing={1} sx={{ textAlign: { xs: 'center', md: 'right' } }}>
            <Typography variant="body2" fontWeight="medium">
              Contact Us
            </Typography>
            <Typography variant="body2" sx={{ opacity: 0.9 }}>
              Email: info@mnair.ng
            </Typography>
            <Typography variant="body2" sx={{ opacity: 0.9 }}>
              Phone: +234 706 572 8972
            </Typography>
          </Stack>
        </Stack>

        <Typography variant="body2" align="center" sx={{ opacity: 0.8, pt: 2, borderTop: '1px solid rgba(255,255,255,0.2)' }}>
          © {new Date().getFullYear()} MNAIR Platform. All rights reserved.
        </Typography>
      </Stack>
    </Container>
  </Box>
)

const App: React.FC = () => {
  const location = useLocation()

  const isPublicRoute = ['/', '/verify'].includes(location.pathname)
  const isLearnRoute = location.pathname === '/learn'
  const isAdminRoute = location.pathname.startsWith('/dashboard')

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {/* Public nav only for non-admin routes */}
      {!isAdminRoute && isPublicRoute && <PublicNavBar />}
      {!isAdminRoute && !isPublicRoute && location.pathname !== '/login' && <PublicNavBar />}
      {/* /learn keeps the nav (64px) but no footer so the chat fills the phone screen */}

      <Box component="main" sx={{ flexGrow: 1, bgcolor: isAdminRoute ? '#f0f2f5' : 'background.default' }}>
        <Routes>
          {/* Public Routes */}
          <Route path="/" element={<Home />} />
          <Route path="/verify" element={<VerifyCertificate />} />
          <Route path="/learn" element={<Learn />} />
          <Route path="/sponsor" element={<SponsorPortal />} />
          <Route path="/payment/callback" element={<PaymentCallback />} />

          {/* Auth Routes */}
          <Route path="/login" element={<Login />} />

          {/* Protected Admin Routes — all wrapped in AdminLayout sidebar */}
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <AdminLayout>
                  <Dashboard />
                </AdminLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/users"
            element={
              <ProtectedRoute>
                <AdminLayout>
                  <UsersReport />
                </AdminLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/lessons"
            element={
              <ProtectedRoute>
                <AdminLayout>
                  <LessonsReport />
                </AdminLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/languages"
            element={
              <ProtectedRoute>
                <AdminLayout>
                  <LanguageReport />
                </AdminLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/engagement"
            element={
              <ProtectedRoute>
                <AdminLayout>
                  <EngagementReport />
                </AdminLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/quiz"
            element={
              <ProtectedRoute>
                <AdminLayout>
                  <QuizReport />
                </AdminLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/channels"
            element={
              <ProtectedRoute>
                <AdminLayout>
                  <ChannelsReport />
                </AdminLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/employers"
            element={
              <ProtectedRoute>
                <AdminLayout>
                  <EmployersReport />
                </AdminLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/sponsors"
            element={
              <ProtectedRoute>
                <AdminLayout>
                  <SponsorsAdmin />
                </AdminLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/sponsors/:id"
            element={
              <ProtectedRoute>
                <AdminLayout>
                  <SponsorDetail />
                </AdminLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/learners"
            element={
              <ProtectedRoute>
                <AdminLayout>
                  <LearnersAdmin />
                </AdminLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/learners/:id"
            element={
              <ProtectedRoute>
                <AdminLayout>
                  <LearnerDetail />
                </AdminLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/certificates"
            element={
              <ProtectedRoute>
                <AdminLayout>
                  <CertificatesAdmin />
                </AdminLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/payments"
            element={
              <ProtectedRoute>
                <AdminLayout>
                  <PaymentsAdmin />
                </AdminLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/audit"
            element={
              <ProtectedRoute>
                <AdminLayout>
                  <AuditLog />
                </AdminLayout>
              </ProtectedRoute>
            }
          />
        </Routes>
      </Box>

      {isPublicRoute && !isLearnRoute && <PublicFooter />}
    </Box>
  )
}

export default App
