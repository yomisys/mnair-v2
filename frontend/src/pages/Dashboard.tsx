import React, { useEffect, useState } from 'react'
import {
  Box,
  Card,
  CardContent,
  Container,
  Grid,
  Typography,
  CircularProgress,
  Alert,
} from '@mui/material'
import {
  People as PeopleIcon,
  School as SchoolIcon,
  EmojiEvents as TrophyIcon,
  TrendingUp as TrendingIcon,
} from '@mui/icons-material'
import { analyticsAPI } from '../services/api'

interface DashboardStats {
  total_users: number
  active_users: number
  completions_today: number
  total_certificates: number
  completion_rate: number
  average_quiz_score: number
}

const StatCard: React.FC<{
  title: string
  value: string | number
  icon: React.ReactElement
  color: string
}> = ({ title, value, icon, color }) => (
  <Card>
    <CardContent>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Box>
          <Typography color="text.secondary" variant="body2" gutterBottom>
            {title}
          </Typography>
          <Typography variant="h4" component="div">
            {value}
          </Typography>
        </Box>
        <Box
          sx={{
            backgroundColor: `${color}15`,
            color: color,
            p: 1.5,
            borderRadius: 2,
            display: 'flex',
          }}
        >
          {icon}
        </Box>
      </Box>
    </CardContent>
  </Card>
)

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        const data = await analyticsAPI.getSummary()
        setStats(data)
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to load dashboard data')
      } finally {
        setIsLoading(false)
      }
    }

    fetchDashboardData()
  }, [])

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <CircularProgress />
      </Box>
    )
  }

  if (error) {
    return (
      <Container>
        <Alert severity="error" sx={{ mt: 4 }}>
          {error}
        </Alert>
      </Container>
    )
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h4" gutterBottom>
        Dashboard Overview
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 4 }}>
        Real-time analytics for the MNAIR platform
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Total Users"
            value={stats?.total_users?.toLocaleString() || 0}
            icon={<PeopleIcon />}
            color="#1976D2"
          />
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Active Users"
            value={stats?.active_users?.toLocaleString() || 0}
            icon={<TrendingIcon />}
            color="#2E7D32"
          />
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Completions Today"
            value={stats?.completions_today?.toLocaleString() || 0}
            icon={<SchoolIcon />}
            color="#ED6C02"
          />
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Total Certificates"
            value={stats?.total_certificates?.toLocaleString() || 0}
            icon={<TrophyIcon />}
            color="#9C27B0"
          />
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Completion Rate
              </Typography>
              <Typography variant="h3" color="primary">
                {stats?.completion_rate?.toFixed(1) || 0}%
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                Users who completed all 7 days
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Average Quiz Score
              </Typography>
              <Typography variant="h3" color="success.main">
                {stats?.average_quiz_score?.toFixed(1) || 0}%
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                Pass rate: 60% required
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Box sx={{ mt: 4 }}>
        <Alert severity="info">
          This is a simplified MVP dashboard. Full analytics with charts will be available in the complete version.
        </Alert>
      </Box>
    </Container>
  )
}

export default Dashboard
