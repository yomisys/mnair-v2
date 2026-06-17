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
  Chip,
} from '@mui/material'
import {
  People as PeopleIcon,
  School as SchoolIcon,
  EmojiEvents as TrophyIcon,
  TrendingUp as TrendingIcon,
  Business as BusinessIcon,
  CheckCircle as CheckIcon,
} from '@mui/icons-material'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import { Line, Bar, Doughnut } from 'react-chartjs-2'
import { analyticsAPI } from '../services/api'
import { format, subDays } from 'date-fns'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

const GREEN = '#1B8A4E'
const LIGHT_GREEN = '#4CAF50'
const COLORS = ['#1B8A4E', '#4CAF50', '#81C784', '#A5D6A7', '#C8E6C9']

interface DashboardData {
  summary: {
    total_users: number
    active_users_7d: number
    users_completed_program: number
    completion_rate: number
    average_quiz_score: number
    certificates_issued: number
    total_employers: number
    user_retention_rate: number
    daily_active_rate: number
  }
  language_distribution: { language: string; user_count: number; percentage: number }[]
  day_distribution: { day: number; user_count: number; percentage: number }[]
  network_distribution: { network: string; user_count: number; percentage: number }[]
  user_growth_trend: { date: string; value: number }[]
  completion_trend: { date: string; value: number }[]
  last_updated: string
}

const StatCard: React.FC<{
  title: string
  value: string | number
  icon: React.ReactElement
  color: string
  sub?: string
}> = ({ title, value, icon, color, sub }) => (
  <Card sx={{ height: '100%' }}>
    <CardContent>
      <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <Box>
          <Typography color="text.secondary" variant="body2" gutterBottom>
            {title}
          </Typography>
          <Typography variant="h4" component="div" fontWeight={700}>
            {value}
          </Typography>
          {sub && (
            <Typography variant="caption" color="text.secondary">
              {sub}
            </Typography>
          )}
        </Box>
        <Box
          sx={{
            backgroundColor: `${color}18`,
            color,
            p: 1.5,
            borderRadius: 2,
            display: 'flex',
            flexShrink: 0,
          }}
        >
          {icon}
        </Box>
      </Box>
    </CardContent>
  </Card>
)

const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English',
  ha: 'Hausa',
  ig: 'Igbo',
  pid: 'Pidgin',
  yo: 'Yoruba',
}

const Dashboard: React.FC = () => {
  const [data, setData] = useState<DashboardData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const result = await analyticsAPI.getDashboard()
        setData(result)
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to load dashboard data')
      } finally {
        setIsLoading(false)
      }
    }
    load()
  }, [])

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <CircularProgress color="success" />
      </Box>
    )
  }

  if (error) {
    return (
      <Container>
        <Alert severity="error" sx={{ mt: 4 }}>{error}</Alert>
      </Container>
    )
  }

  const s = data!.summary

  // User growth line chart
  const growthLabels = data!.user_growth_trend.map(p => format(new Date(p.date), 'MMM d'))
  const growthValues = data!.user_growth_trend.map(p => p.value)
  const growthChart = {
    labels: growthLabels,
    datasets: [{
      label: 'Total Users',
      data: growthValues,
      borderColor: GREEN,
      backgroundColor: `${GREEN}20`,
      fill: true,
      tension: 0.4,
      pointRadius: 4,
      pointBackgroundColor: GREEN,
    }],
  }

  // Completion trend line chart
  const completionLabels = data!.completion_trend.map(p => format(new Date(p.date), 'MMM d'))
  const completionValues = data!.completion_trend.map(p => p.value)
  const completionChart = {
    labels: completionLabels,
    datasets: [{
      label: 'Completion Rate (%)',
      data: completionValues,
      borderColor: LIGHT_GREEN,
      backgroundColor: `${LIGHT_GREEN}20`,
      fill: true,
      tension: 0.4,
      pointRadius: 4,
      pointBackgroundColor: LIGHT_GREEN,
    }],
  }

  // Day distribution bar chart
  const dayLabels = Array.from({ length: 7 }, (_, i) => `Day ${i + 1}`)
  const dayValues = dayLabels.map((_, i) => {
    const found = data!.day_distribution.find(d => d.day === i + 1)
    return found?.user_count ?? 0
  })
  const dayChart = {
    labels: dayLabels,
    datasets: [{
      label: 'Users at Day',
      data: dayValues,
      backgroundColor: COLORS[0],
      borderRadius: 6,
      hoverBackgroundColor: COLORS[1],
    }],
  }

  // Language doughnut
  const langLabels = data!.language_distribution.map(l => LANGUAGE_NAMES[l.language] || l.language)
  const langValues = data!.language_distribution.map(l => l.user_count)
  const langChart = {
    labels: langLabels,
    datasets: [{
      data: langValues,
      backgroundColor: COLORS,
      borderWidth: 2,
      borderColor: '#fff',
    }],
  }

  // Network doughnut
  const netLabels = data!.network_distribution.map(n => n.network)
  const netValues = data!.network_distribution.map(n => n.user_count)
  const netChart = {
    labels: netLabels,
    datasets: [{
      data: netValues,
      backgroundColor: ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF'],
      borderWidth: 2,
      borderColor: '#fff',
    }],
  }

  const lineOptions = {
    responsive: true,
    plugins: { legend: { display: false } },
    scales: {
      y: { beginAtZero: true, grid: { color: '#f0f0f0' } },
      x: { grid: { display: false } },
    },
  }

  const barOptions = {
    responsive: true,
    plugins: { legend: { display: false } },
    scales: {
      y: { beginAtZero: true, ticks: { stepSize: 1 }, grid: { color: '#f0f0f0' } },
      x: { grid: { display: false } },
    },
  }

  const doughnutOptions = {
    responsive: true,
    plugins: {
      legend: { position: 'bottom' as const, labels: { padding: 12, font: { size: 12 } } },
    },
    cutout: '65%',
  }

  const updatedAt = data!.last_updated
    ? format(new Date(data!.last_updated), 'MMM d, yyyy HH:mm')
    : ''

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 6 }}>
      <Box sx={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', mb: 0.5 }}>
        <Typography variant="h4" fontWeight={700}>Dashboard</Typography>
        {updatedAt && (
          <Typography variant="caption" color="text.secondary">Updated {updatedAt}</Typography>
        )}
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 4 }}>
        Real-time analytics for the MNAIR platform
      </Typography>

      {/* Stat cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={6} sm={4} md={2}>
          <StatCard title="Total Users" value={s.total_users.toLocaleString()} icon={<PeopleIcon />} color="#1976D2" />
        </Grid>
        <Grid item xs={6} sm={4} md={2}>
          <StatCard title="Active (7d)" value={s.active_users_7d.toLocaleString()} icon={<TrendingIcon />} color={GREEN} sub={`${s.daily_active_rate.toFixed(0)}% daily rate`} />
        </Grid>
        <Grid item xs={6} sm={4} md={2}>
          <StatCard title="Completed" value={s.users_completed_program.toLocaleString()} icon={<CheckIcon />} color="#2E7D32" sub={`${s.completion_rate.toFixed(1)}% rate`} />
        </Grid>
        <Grid item xs={6} sm={4} md={2}>
          <StatCard title="Certificates" value={s.certificates_issued.toLocaleString()} icon={<TrophyIcon />} color="#9C27B0" />
        </Grid>
        <Grid item xs={6} sm={4} md={2}>
          <StatCard title="Avg Quiz" value={`${s.average_quiz_score.toFixed(1)}%`} icon={<SchoolIcon />} color="#ED6C02" sub="60% pass required" />
        </Grid>
        <Grid item xs={6} sm={4} md={2}>
          <StatCard title="Employers" value={s.total_employers.toLocaleString()} icon={<BusinessIcon />} color="#0288D1" />
        </Grid>
      </Grid>

      {/* Growth charts */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>User Growth</Typography>
              <Line data={growthChart} options={lineOptions} />
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>Completion Rate Trend</Typography>
              <Line data={completionChart} options={lineOptions} />
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Day distribution + Language + Network */}
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>Users by Program Day</Typography>
              <Typography variant="caption" color="text.secondary">Where learners currently are</Typography>
              <Box sx={{ mt: 1 }}>
                <Bar data={dayChart} options={barOptions} />
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>Language</Typography>
              {langValues.every(v => v === 0) ? (
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 180 }}>
                  <Typography variant="body2" color="text.secondary">No data yet</Typography>
                </Box>
              ) : (
                <Doughnut data={langChart} options={doughnutOptions} />
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>Network</Typography>
              {netValues.every(v => v === 0) ? (
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 180 }}>
                  <Typography variant="body2" color="text.secondary">No data yet</Typography>
                </Box>
              ) : (
                <Doughnut data={netChart} options={doughnutOptions} />
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Container>
  )
}

export default Dashboard
