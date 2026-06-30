import React, { useEffect, useState } from 'react'
import {
  Box, Card, CardContent, Container, Typography, CircularProgress, Alert,
  Grid, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
} from '@mui/material'
import { Bar, Line } from 'react-chartjs-2'
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, PointElement,
  LineElement, Title, Tooltip, Legend, Filler,
} from 'chart.js'
import { analyticsAPI } from '../services/api'
import ExportButton from '../components/ExportButton'

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Title, Tooltip, Legend, Filler)

interface FunnelRow {
  day: number; users_reached: number; users_completed_day: number
  dropoff_from_prev: number; cumulative_dropoff: number
}

const EngagementReport: React.FC = () => {
  const [data, setData] = useState<FunnelRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    analyticsAPI.getEngagement()
      .then(setData)
      .catch(e => setError(e.response?.data?.detail || 'Failed to load'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>
  if (error) return <Container sx={{ mt: 4 }}><Alert severity="error">{error}</Alert></Container>

  const labels = data.map(r => `Day ${r.day}`)
  const funnelChart = {
    labels,
    datasets: [
      {
        label: 'Users Reached Day',
        data: data.map(r => r.users_reached),
        backgroundColor: '#1B8A4E',
        borderRadius: 6,
      },
      {
        label: 'Users Completed Day',
        data: data.map(r => r.users_completed_day),
        backgroundColor: '#4CAF50aa',
        borderRadius: 6,
      },
    ],
  }
  const dropoffChart = {
    labels,
    datasets: [
      {
        label: 'Cumulative Dropout %',
        data: data.map(r => r.cumulative_dropoff),
        borderColor: '#F44336',
        backgroundColor: '#F4433620',
        fill: true,
        tension: 0.4,
        pointRadius: 5,
        pointBackgroundColor: '#F44336',
      },
      {
        label: 'Step Dropoff %',
        data: data.map(r => r.dropoff_from_prev),
        borderColor: '#FF9800',
        backgroundColor: 'transparent',
        tension: 0.4,
        pointRadius: 5,
        pointBackgroundColor: '#FF9800',
        borderDash: [5, 5],
      },
    ],
  }

  const maxUsers = data[0]?.users_reached || 1
  const exportData = data.map(r => ({
    day: r.day, users_reached: r.users_reached, users_completed_day: r.users_completed_day,
    retention_pct: ((r.users_reached / maxUsers) * 100).toFixed(1),
    dropoff_from_prev: r.dropoff_from_prev, cumulative_dropoff: r.cumulative_dropoff,
  }))

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 6 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Box>
          <Typography variant="h5" fontWeight={700}>Engagement & Dropout Funnel</Typography>
          <Typography variant="body2" color="text.secondary">Where learners drop off in the 7-day program</Typography>
        </Box>
        <ExportButton data={exportData as any} filename="engagement_report.csv" />
      </Box>

      {/* Summary cards */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: 'Total Starters', value: data[0]?.users_reached ?? 0, color: '#1B8A4E' },
          { label: 'Day 7 Completers', value: data[6]?.users_completed_day ?? 0, color: '#4CAF50' },
          {
            label: 'Overall Retention',
            value: `${((data[6]?.users_reached ?? 0) / (data[0]?.users_reached || 1) * 100).toFixed(1)}%`,
            color: '#2196F3',
          },
          {
            label: 'Biggest Dropoff',
            value: data.length ? `Day ${data.reduce((a, b) => a.dropoff_from_prev > b.dropoff_from_prev ? a : b).day}` : '—',
            color: '#F44336',
          },
        ].map(c => (
          <Grid item xs={6} sm={3} key={c.label}>
            <Card>
              <CardContent sx={{ textAlign: 'center', py: 2 }}>
                <Typography variant="h4" fontWeight={700} color={c.color}>{typeof c.value === 'number' ? c.value.toLocaleString() : c.value}</Typography>
                <Typography variant="caption" color="text.secondary">{c.label}</Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={7}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>Learner Funnel</Typography>
              <Bar
                data={funnelChart}
                options={{
                  responsive: true,
                  plugins: { legend: { position: 'top' } },
                  scales: { y: { beginAtZero: true } },
                }}
              />
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={5}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>Dropout Rate Trend</Typography>
              <Line
                data={dropoffChart}
                options={{
                  responsive: true,
                  plugins: { legend: { position: 'top' } },
                  scales: { y: { beginAtZero: true, max: 100, ticks: { callback: v => `${v}%` } } },
                }}
              />
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Card>
        <CardContent>
          <Typography variant="h6" fontWeight={600} gutterBottom>Day-by-Day Breakdown</Typography>
          <TableContainer component={Paper} elevation={0}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  {['Day', 'Users Reached', 'Completed Day', 'Retention %', 'Step Dropoff %', 'Cumulative Dropout %'].map(h => (
                    <TableCell key={h} sx={{ fontWeight: 700, bgcolor: '#f5f6fa' }}>{h}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {data.map(r => (
                  <TableRow key={r.day} hover>
                    <TableCell><strong>Day {r.day}</strong></TableCell>
                    <TableCell>{r.users_reached.toLocaleString()}</TableCell>
                    <TableCell>{r.users_completed_day.toLocaleString()}</TableCell>
                    <TableCell>
                      <Typography variant="body2" color="success.main" fontWeight={600}>
                        {((r.users_reached / maxUsers) * 100).toFixed(1)}%
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color={r.dropoff_from_prev > 20 ? 'error.main' : 'text.secondary'}>
                        {r.dropoff_from_prev > 0 ? `-${r.dropoff_from_prev}%` : '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color={r.cumulative_dropoff > 50 ? 'error.main' : 'warning.main'}>
                        {r.cumulative_dropoff}%
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    </Container>
  )
}

export default EngagementReport
