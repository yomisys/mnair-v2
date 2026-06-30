import React, { useEffect, useState } from 'react'
import {
  Box, Card, CardContent, Container, Typography, CircularProgress, Alert,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  Grid, LinearProgress,
} from '@mui/material'
import { Bar, Doughnut } from 'react-chartjs-2'
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, ArcElement,
  Title, Tooltip, Legend,
} from 'chart.js'
import { analyticsAPI } from '../services/api'
import ExportButton from '../components/ExportButton'

ChartJS.register(CategoryScale, LinearScale, BarElement, ArcElement, Title, Tooltip, Legend)

const LANG_NAMES: Record<string, string> = {
  en: 'English', ha: 'Hausa', ig: 'Igbo', pid: 'Pidgin', yo: 'Yoruba',
  ENGLISH: 'English', HAUSA: 'Hausa', IGBO: 'Igbo', PIDGIN: 'Pidgin', YORUBA: 'Yoruba',
}
const COLORS = ['#1B8A4E', '#2196F3', '#FF9800', '#9C27B0', '#F44336']

interface LangRow {
  language: string; total_users: number; completed_users: number
  completion_rate: number; avg_quiz_score: number; dropout_rate: number
}

const LanguageReport: React.FC = () => {
  const [data, setData] = useState<LangRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    analyticsAPI.getLanguages()
      .then(setData)
      .catch(e => setError(e.response?.data?.detail || 'Failed to load'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>
  if (error) return <Container sx={{ mt: 4 }}><Alert severity="error">{error}</Alert></Container>

  const labels = data.map(r => LANG_NAMES[r.language] ?? r.language)
  const completionChart = {
    labels,
    datasets: [
      { label: 'Completion Rate %', data: data.map(r => r.completion_rate), backgroundColor: '#1B8A4E', borderRadius: 6 },
      { label: 'Avg Quiz Score %', data: data.map(r => r.avg_quiz_score), backgroundColor: '#4CAF50aa', borderRadius: 6 },
    ],
  }
  const doughnutChart = {
    labels,
    datasets: [{ data: data.map(r => r.total_users), backgroundColor: COLORS, borderWidth: 2, borderColor: '#fff' }],
  }

  const exportData = data.map(r => ({
    language: LANG_NAMES[r.language] ?? r.language,
    total_users: r.total_users, completed_users: r.completed_users,
    completion_rate: r.completion_rate, avg_quiz_score: r.avg_quiz_score,
    dropout_rate: r.dropout_rate,
  }))

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 6 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Box>
          <Typography variant="h5" fontWeight={700}>Language Performance</Typography>
          <Typography variant="body2" color="text.secondary">Completion and quiz scores by learner language</Typography>
        </Box>
        <ExportButton data={exportData as any} filename="language_report.csv" />
      </Box>

      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>Completion Rate vs Quiz Score by Language</Typography>
              <Bar
                data={completionChart}
                options={{
                  responsive: true,
                  plugins: { legend: { position: 'top' } },
                  scales: { y: { beginAtZero: true, max: 100, ticks: { callback: v => `${v}%` } } },
                }}
              />
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>User Distribution</Typography>
              {data.every(r => r.total_users === 0) ? (
                <Typography variant="body2" color="text.secondary">No data</Typography>
              ) : (
                <Doughnut
                  data={doughnutChart}
                  options={{ plugins: { legend: { position: 'bottom', labels: { padding: 12 } } }, cutout: '65%' }}
                />
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Card>
        <CardContent>
          <Typography variant="h6" fontWeight={600} gutterBottom>Language Breakdown</Typography>
          <TableContainer component={Paper} elevation={0}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  {['Language', 'Total Users', 'Completed', 'Completion Rate', 'Avg Quiz Score', 'Dropout Rate'].map(h => (
                    <TableCell key={h} sx={{ fontWeight: 700, bgcolor: '#f5f6fa' }}>{h}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {data.map(r => (
                  <TableRow key={r.language} hover>
                    <TableCell><strong>{LANG_NAMES[r.language] ?? r.language}</strong></TableCell>
                    <TableCell>{r.total_users.toLocaleString()}</TableCell>
                    <TableCell>{r.completed_users.toLocaleString()}</TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <LinearProgress
                          variant="determinate" value={r.completion_rate}
                          sx={{ width: 80, height: 8, borderRadius: 4, bgcolor: '#e0e0e0', '& .MuiLinearProgress-bar': { bgcolor: '#1B8A4E' } }}
                        />
                        <Typography variant="body2">{r.completion_rate}%</Typography>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" fontWeight={600} color={r.avg_quiz_score >= 60 ? 'success.main' : 'error.main'}>
                        {r.avg_quiz_score}%
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color={r.dropout_rate > 50 ? 'error.main' : 'text.secondary'}>
                        {r.dropout_rate}%
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

export default LanguageReport
