import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Box, AppBar, Toolbar, Typography, Button, Container } from '@mui/material'
import { Logout as LogoutIcon } from '@mui/icons-material'
import { useAuth } from './contexts/AuthContext'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'

const ProtectedRoute: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return <div>Loading...</div>
  }

  return isAuthenticated ? children : <Navigate to="/login" />
}

const App: React.FC = () => {
  const { isAuthenticated, user, logout } = useAuth()

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {isAuthenticated && (
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
      )}

      <Box component="main" sx={{ flexGrow: 1, bgcolor: 'background.default' }}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route path="/" element={<Navigate to="/dashboard" />} />
        </Routes>
      </Box>

      {isAuthenticated && (
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
