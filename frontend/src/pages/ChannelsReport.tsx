import React, { useEffect, useState } from 'react'
import {
  Box, Card, CardContent, Container, Typography, CircularProgress, Alert,
  Grid, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  LinearProgress,
} from '@mui/material'
import { Doughnut, Bar } from 'react-chartjs-2'
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, ArcElement,
  Title, Tooltip, Legend,
} from 'chart.js'
import { analyticsAPI } from '../services/api'
import ExportButton from '../components/ExportButton'

ChartJS.register(CategoryScale, LinearScale, BarElement, ArcElement, Title, Tooltip, Legend)

const CHANNEL_COLORS: Record<string, string> = {
  telegram: '#229ED9', web: '#1B7A3E', webpush: '#43A047', ussd: '#FF9800', sms: '#2196F3',
  kingschat: '#7B1FA2', whatsapp: '#9E9E9E', unknown: '#9E9E9E',
}
const CHANNEL_LABELS: Record<string, string> = {
  telegram: 'Telegram', web: 'Web app', webpush: 'Web Push', ussd: 'USSD', sms: 'SMS',
  kingschat: 'KingsChat', whatsapp: 'WhatsApp (legacy)', unknown: 'Unknown',
}

interface ChannelRow {
  channel: string; unique_users: number; lesson_starts: number
  lesson_completions: number; completion_rate: number; avg_score: number | null
}

const ChannelsReport: React.FC = () => {
  const [data, setData] = useState<ChannelRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    analyticsAPI.getChannels()
      .then(setData)
      .catch(e => setError(e.response?.data?.detail || 'Failed to load'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>
  if (error) return <Container sx={{ mt: 4 }}><Alert severity="error">{error}</Alert></Container>

  const labels = data.map(r => CHANNEL_LABELS[r.channel] ?? r.channel)
  const colors = data.map(r => CHANNEL_COLORS[r.channel] ?? '#9E9E9E')

  const doughnutChart = {
    labels,
    datasets: [{ data: data.map(r => r.unique_users), backgroundColor: colors, borderWidth: 2, borderColor: '#fff' }],
  }
  const barChart = {
    labels,
    datasets: [
      { label: 'Starts', data: data.map(r => r.lesson_starts), backgroundColor: colors.map(c => `${c}99`), borderRadius: 6 },
      { label: 'Completions', data: data.map(r => r.lesson_completions), backgroundColor: colors, borderRadius: 6 },
    ],
  }

  const exportData = data.map(r => ({
    channel: CHANNEL_LABELS[r.channel] ?? r.channel,
    unique_users: r.unique_users, lesson_starts: r.lesson_starts,
    lesson_completions: r.lesson_completions, completion_rate: r.completion_rate,
    avg_score: r.avg_score,
  }))

  const best = data.reduce((a, b) => ((a.completion_rate ?? 0) > (b.completion_rate ?? 0) ? a : b), data[0])

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 6 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Box>
          <Typography variant="h5" fontWeight={700}>Channel Performance</Typography>
          <Typography variant="body2" color="text.secondary">Telegram vs Web vs USSD vs SMS delivery breakdown</Typography>
        </Box>
        <ExportButton data={exportData as any} filename="channels_report.csv" />
      </Box>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: 'Total Channels', value: data.length, color: '#1B8A4E' },
          { label: 'Total Starts', value: data.reduce((s, r) => s + r.lesson_starts, 0).toLocaleString(), color: '#2196F3' },
          { label: 'Total Completions', value: data.reduce((s, r) => s + r.lesson_completions, 0).toLocaleString(), color: '#4CAF50' },
          { label: 'Best Channel', value: best ? (CHANNEL_LABELS[best.channel] ?? best.channel) : '—', color: '#FF9800' },
        ].map(c => (
          <Grid item xs={6} sm={3} key={c.label}>
            <Card>
              <CardContent sx={{ textAlign: 'center', py: 2 }}>
                <Typography variant="h5" fontWeight={700} color={c.color}>{c.value}</Typography>
                <Typography variant="caption" color="text.secondary">{c.label}</Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={4}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>Users by Channel</Typography>
              {data.every(r => r.unique_users === 0) ? (
                <Typography variant="body2" color="text.secondary">No data yet</Typography>
              ) : (
                <Doughnut
                  data={doughnutChart}
                  options={{ plugins: { legend: { position: 'bottom', labels: { padding: 12 } } }, cutout: '65%' }}
                />
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>Lesson Starts vs Completions</Typography>
              <Bar
                data={barChart}
                options={{
                  responsive: true,
                  plugins: { legend: { position: 'top' } },
                  scales: { y: { beginAtZero: true } },
                }}
              />
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Card>
        <CardContent>
          <Typography variant="h6" fontWeight={600} gutterBottom>Channel Details</Typography>
          <TableContainer component={Paper} elevation={0}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  {['Channel', 'Unique Users', 'Lesson Starts', 'Completions', 'Completion Rate', 'Avg Score'].map(h => (
                    <TableCell key={h} sx={{ fontWeight: 700, bgcolor: '#f5f6fa' }}>{h}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {data.map(r => (
                  <TableRow key={r.channel} hover>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: CHANNEL_COLORS[r.channel] ?? '#9E9E9E' }} />
                        <strong>{CHANNEL_LABELS[r.channel] ?? r.channel}</strong>
                      </Box>
                    </TableCell>
                    <TableCell>{r.unique_users.toLocaleString()}</TableCell>
                    <TableCell>{r.lesson_starts.toLocaleString()}</TableCell>
                    <TableCell>{r.lesson_completions.toLocaleString()}</TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <LinearProgress
                          variant="determinate" value={r.completion_rate}
                          sx={{ width: 80, height: 8, borderRadius: 4, bgcolor: '#e0e0e0', '& .MuiLinearProgress-bar': { bgcolor: CHANNEL_COLORS[r.channel] ?? '#9E9E9E' } }}
                        />
                        <Typography variant="body2">{r.completion_rate}%</Typography>
                      </Box>
                    </TableCell>
                    <TableCell>
                      {r.avg_score != null ? (
                        <Typography variant="body2" fontWeight={600} color={r.avg_score >= 60 ? 'success.main' : 'error.main'}>
                          {r.avg_score}%
                        </Typography>
                      ) : '—'}
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

export default ChannelsReport
