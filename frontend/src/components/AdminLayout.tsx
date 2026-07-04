import React, { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  Box, Drawer, Typography, List, ListItemButton,
  ListItemIcon, ListItemText, IconButton, Divider, Avatar, Tooltip,
} from '@mui/material'
import {
  Dashboard as DashboardIcon,
  MenuBook as LessonsIcon,
  Language as LanguageIcon,
  TrendingDown as EngagementIcon,
  Quiz as QuizIcon,
  Business as EmployersIcon,
  Logout as LogoutIcon,
  Menu as MenuIcon,
  ChevronLeft as ChevronLeftIcon,
  CellTower as ChannelIcon,
  People as PeopleIcon,
} from '@mui/icons-material'
import { useAuth } from '../contexts/AuthContext'

const DRAWER_WIDTH = 220
const DRAWER_MINI = 64

const NAV = [
  { label: 'Overview', path: '/dashboard', icon: <DashboardIcon /> },
  { label: 'Users', path: '/dashboard/users', icon: <PeopleIcon /> },
  { label: 'Lessons', path: '/dashboard/lessons', icon: <LessonsIcon /> },
  { label: 'Languages', path: '/dashboard/languages', icon: <LanguageIcon /> },
  { label: 'Engagement', path: '/dashboard/engagement', icon: <EngagementIcon /> },
  { label: 'Quiz Analytics', path: '/dashboard/quiz', icon: <QuizIcon /> },
  { label: 'Channels', path: '/dashboard/channels', icon: <ChannelIcon /> },
  { label: 'Employers', path: '/dashboard/employers', icon: <EmployersIcon /> },
]

const AdminLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [open, setOpen] = useState(true)
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const width = open ? DRAWER_WIDTH : DRAWER_MINI

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      {/* Sidebar */}
      <Drawer
        variant="permanent"
        sx={{
          width,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width,
            boxSizing: 'border-box',
            overflowX: 'hidden',
            transition: 'width 0.2s',
            bgcolor: '#1a2332',
            color: '#fff',
            borderRight: 'none',
          },
        }}
      >
        {/* Logo row */}
        <Box sx={{ display: 'flex', alignItems: 'center', px: 2, py: 1.5, minHeight: 56 }}>
          {open && (
            <Typography variant="h6" fontWeight={700} color="#4CAF50" sx={{ flexGrow: 1, fontSize: 16 }}>
              MNAIR Admin
            </Typography>
          )}
          <IconButton onClick={() => setOpen(!open)} size="small" sx={{ color: '#aaa', ml: open ? 0 : 'auto', mr: open ? 0 : 'auto' }}>
            {open ? <ChevronLeftIcon /> : <MenuIcon />}
          </IconButton>
        </Box>

        <Divider sx={{ borderColor: '#2d3f55' }} />

        <List dense sx={{ pt: 1 }}>
          {NAV.map(item => {
            const active = location.pathname === item.path
            return (
              <Tooltip key={item.path} title={open ? '' : item.label} placement="right">
                <ListItemButton
                  onClick={() => navigate(item.path)}
                  selected={active}
                  sx={{
                    mx: 1, borderRadius: 1, mb: 0.5,
                    '&.Mui-selected': { bgcolor: '#4CAF5022', color: '#4CAF50' },
                    '&.Mui-selected .MuiListItemIcon-root': { color: '#4CAF50' },
                    '&:hover': { bgcolor: '#ffffff11' },
                    color: active ? '#4CAF50' : '#b0bec5',
                    minHeight: 44,
                    justifyContent: open ? 'initial' : 'center',
                    px: open ? 2 : 1.5,
                  }}
                >
                  <ListItemIcon sx={{ color: 'inherit', minWidth: open ? 36 : 'auto' }}>
                    {item.icon}
                  </ListItemIcon>
                  {open && <ListItemText primary={item.label} primaryTypographyProps={{ fontSize: 14 }} />}
                </ListItemButton>
              </Tooltip>
            )
          })}
        </List>

        <Box sx={{ mt: 'auto', p: 1.5 }}>
          <Divider sx={{ borderColor: '#2d3f55', mb: 1.5 }} />
          {open ? (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Avatar sx={{ width: 32, height: 32, bgcolor: '#4CAF50', fontSize: 13 }}>
                {user?.name?.[0] ?? 'A'}
              </Avatar>
              <Box sx={{ flex: 1, overflow: 'hidden' }}>
                <Typography variant="caption" color="#eee" noWrap display="block">{user?.name}</Typography>
                <Typography variant="caption" color="#78909c" noWrap display="block">{user?.role}</Typography>
              </Box>
              <IconButton size="small" onClick={logout} sx={{ color: '#78909c' }}>
                <LogoutIcon fontSize="small" />
              </IconButton>
            </Box>
          ) : (
            <Tooltip title="Logout" placement="right">
              <IconButton onClick={logout} sx={{ color: '#78909c', mx: 'auto', display: 'flex' }}>
                <LogoutIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Box>
      </Drawer>

      {/* Main content */}
      <Box sx={{ flexGrow: 1, overflow: 'auto', bgcolor: '#f5f6fa' }}>
        {children}
      </Box>
    </Box>
  )
}

export default AdminLayout
