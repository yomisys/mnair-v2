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
import { Logout as LogoutIcon, VerifiedUser as VerifyIcon } from '@mui/icons-material'
import { useAuth } from './contexts/AuthContext'
import Home from './pages/Home'
import VerifyCertificate from './pages/VerifyCertificate'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'

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

const AdminNavBar: React.FC = () => {
  const { user, logout } = useAuth()

  return (
    <AppBar position="static" elevation={1}>
      <Toolbar>
        <Typography variant="h6" component="div" sx={{ flexGrow: 1, fontWeight: 'bold' }}>
          MNAIR Admin
        </Typography>
        <Typography variant="body2" sx={{ mr: 2 }}>
          {user?.name} ({user?.role})
        </Typography>
        <Button color="inherit" startIcon={<LogoutIcon />} onClick={logout}>
          Logout
        </Button>
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
              Email: support@mnair.gov.ng
            </Typography>
            <Typography variant="body2" sx={{ opacity: 0.9 }}>
              WhatsApp: +234 XXX XXX XXXX
            </Typography>
          </Stack>
        </Stack>

        <Typography variant="body2" align="center" sx={{ opacity: 0.8, pt: 2, borderTop: '1px solid rgba(255,255,255,0.2)' }}>
          © {new Date().getFullYear()} MNAIR Platform - Federal Government of Nigeria. All rights reserved.
        </Typography>
      </Stack>
    </Container>
  </Box>
)

const App: React.FC = () => {
  const { isAuthenticated } = useAuth()
  const location = useLocation()

  // Determine if current route is public or admin
  const isPublicRoute = ['/', '/verify'].includes(location.pathname)
  const isAdminRoute = location.pathname.startsWith('/dashboard')

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {/* Navigation Bar */}
      {isAuthenticated && isAdminRoute ? (
        <AdminNavBar />
      ) : isPublicRoute ? (
        <PublicNavBar />
      ) : null}

      {/* Main Content */}
      <Box component="main" sx={{ flexGrow: 1, bgcolor: 'background.default' }}>
        <Routes>
          {/* Public Routes */}
          <Route path="/" element={<Home />} />
          <Route path="/verify" element={<VerifyCertificate />} />

          {/* Auth Routes */}
          <Route path="/login" element={<Login />} />

          {/* Protected Admin Routes */}
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
        </Routes>
      </Box>

      {/* Footer */}
      {isPublicRoute && <PublicFooter />}
      {isAuthenticated && isAdminRoute && (
        <Box
          component="footer"
          sx={{
            py: 2,
            px: 2,
            mt: 'auto',
            backgroundColor: 'background.paper',
            borderTop: '1px solid',
            borderColor: 'divider',
          }}
        >
          <Container maxWidth="lg">
            <Typography variant="body2" color="text.secondary" align="center">
              MNAIR Platform - Make Nigeria AI Ready © {new Date().getFullYear()}
            </Typography>
          </Container>
        </Box>
      )}
    </Box>
  )
}

export default App
