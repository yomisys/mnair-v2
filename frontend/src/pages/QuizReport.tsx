import React, { useEffect, useState } from 'react'
import {
  Box, Card, CardContent, Container, Typography, CircularProgress, Alert,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  Grid, Chip, MenuItem, Select, FormControl, InputLabel, LinearProgress,
} from '@mui/material'
import { Bar } from 'react-chartjs-2'
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend } from 'chart.js'
import { analyticsAPI } from '../services/api'
import ExportButton from '../components/ExportButton'

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend)

const LANG_NAMES: Record<string, string> = {
  en: 'English', ha: 'Hausa', ig: 'Igbo', pid: 'Pidgin', yo: 'Yoruba', '': 'All',
  ENGLISH: 'English', HAUSA: 'Hausa', IGBO: 'Igbo', PIDGIN: 'Pidgin', YORUBA: 'Yoruba',
}
const TOPIC_LABELS: Record<string, string> = {
  what_is_ai: 'What is AI', how_ai_works: 'How AI Works',
  ai_in_nigeria: 'AI in Nigeria', ai_tools: 'AI Tools', ai_ethics: 'AI Ethics',
}

interface QuizRow {
  lesson_id: string; db_id: number; day: number; topic: string; language: string; title: string
  total_attempts: number; unique_takers: number; pass_rate: number; avg_score: number; retry_rate: number
  avg_score_attempt1: number | null; avg_score_attempt2: number | null; avg_score_attempt3: number | null
}

const QuizReport: React.FC = () => {
  const [data, setData] = useState<QuizRow[]>([])
  const [lang, setLang] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    analyticsAPI.getQuiz(lang || undefined)
      .then(setData)
      .catch(e => setError(e.response?.data?.detail || 'Failed to load'))
      .finally(() => setLoading(false))
  }, [lang])

  const hardest = [...data].sort((a, b) => a.pass_rate - b.pass_rate).slice(0, 8)
  const retryChart = {
    labels: hardest.map(r => `D${r.day} ${TOPIC_LABELS[r.topic]?.split(' ')[0] ?? r.topic}`),
    datasets: [
      { label: 'Pass Rate %', data: hardest.map(r => r.pass_rate), backgroundColor: '#1B8A4E', borderRadius: 4 },
      { label: 'Retry Rate %', data: hardest.map(r => r.retry_rate), backgroundColor: '#FF9800aa', borderRadius: 4 },
    ],
  }

  const exportData = data.map(r => ({
    lesson_id: r.lesson_id, day: r.day, topic: r.topic, language: r.language,
    total_attempts: r.total_attempts, unique_takers: r.unique_takers,
    pass_rate: r.pass_rate, avg_score: r.avg_score, retry_rate: r.retry_rate,
    avg_score_attempt1: r.avg_score_attempt1, avg_score_attempt2: r.avg_score_attempt2,
    avg_score_attempt3: r.avg_score_attempt3,
  }))

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>
  if (error) return <Container sx={{ mt: 4 }}><Alert severity="error">{error}</Alert></Container>

  const overallPassRate = data.length ? (data.reduce((s, r) => s + r.pass_rate, 0) / data.length).toFixed(1) : '—'
  const highRetry = data.filter(r => r.retry_rate > 30).length

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 6 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Box>
          <Typography variant="h5" fontWeight={700}>Quiz Analytics</Typography>
          <Typography variant="body2" color="text.secondary">Pass rates, retry patterns, and score progression</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Language</InputLabel>
            <Select value={lang} label="Language" onChange={e => setLang(e.target.value)}>
              {Object.entries(LANG_NAMES).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
            </Select>
          </FormControl>
          <ExportButton data={exportData as any} filename="quiz_report.csv" />
        </Box>
      </Box>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: 'Overall Pass Rate', value: `${overallPassRate}%`, color: '#1B8A4E' },
          { label: 'Total Attempts', value: data.reduce((s, r) => s + r.total_attempts, 0).toLocaleString(), color: '#2196F3' },
          { label: 'High Retry Lessons', value: highRetry, color: '#FF9800' },
          { label: 'Lessons Tracked', value: data.length, color: '#9C27B0' },
        ].map(c => (
          <Grid item xs={6} sm={3} key={c.label}>
            <Card>
              <CardContent sx={{ textAlign: 'center', py: 2 }}>
                <Typography variant="h4" fontWeight={700} color={c.color}>{c.value}</Typography>
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
              <Typography variant="h6" fontWeight={600} gutterBottom>Hardest Lessons: Pass Rate vs Retry Rate</Typography>
              <Bar
                data={retryChart}
                options={{
                  responsive: true,
                  plugins: { legend: { position: 'top' } },
                  scales: { y: { beginAtZero: true, max: 100, ticks: { callback: v => `${v}%` } } },
                }}
              />
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={5}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>Score Improvement on Retry</Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
                Avg score by attempt number (lessons with retries)
              </Typography>
              {data.filter(r => r.avg_score_attempt2 !== null).slice(0, 6).map(r => (
                <Box key={r.lesson_id} sx={{ mb: 2 }}>
                  <Typography variant="caption" color="text.secondary" noWrap display="block">
                    D{r.day} {TOPIC_LABELS[r.topic] ?? r.topic} ({LANG_NAMES[r.language]})
                  </Typography>
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    {[r.avg_score_attempt1, r.avg_score_attempt2, r.avg_score_attempt3].map((v, i) =>
                      v !== null && (
                        <Chip
                          key={i}
                          label={`Att ${i + 1}: ${v}%`}
                          size="small"
                          color={i === 0 ? 'default' : v > (r.avg_score_attempt1 ?? 0) ? 'success' : 'error'}
                          variant={i === 0 ? 'outlined' : 'filled'}
                        />
                      )
                    )}
                  </Box>
                </Box>
              ))}
              {!data.some(r => r.avg_score_attempt2 !== null) && (
                <Typography variant="body2" color="text.secondary">No retry data yet</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Card>
        <CardContent>
          <Typography variant="h6" fontWeight={600} gutterBottom>All Quiz Statistics</Typography>
          <TableContainer component={Paper} elevation={0} sx={{ maxHeight: 520 }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  {['Day', 'Topic', 'Lang', 'Takers', 'Attempts', 'Pass Rate', 'Avg Score', 'Retry Rate', 'Att 1', 'Att 2', 'Att 3'].map(h => (
                    <TableCell key={h} sx={{ fontWeight: 700, bgcolor: '#f5f6fa' }}>{h}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {data.map(r => (
                  <TableRow key={r.lesson_id} hover>
                    <TableCell><Chip label={`Day ${r.day}`} size="small" /></TableCell>
                    <TableCell sx={{ maxWidth: 140 }}><Typography variant="caption" noWrap>{TOPIC_LABELS[r.topic] ?? r.topic}</Typography></TableCell>
                    <TableCell><Chip label={r.language} size="small" variant="outlined" /></TableCell>
                    <TableCell>{r.unique_takers}</TableCell>
                    <TableCell>{r.total_attempts}</TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <LinearProgress
                          variant="determinate" value={r.pass_rate}
                          sx={{ width: 50, height: 6, borderRadius: 3, bgcolor: '#e0e0e0', '& .MuiLinearProgress-bar': { bgcolor: r.pass_rate >= 60 ? '#4CAF50' : '#f44336' } }}
                        />
                        <Typography variant="caption">{r.pass_rate}%</Typography>
                      </Box>
                    </TableCell>
                    <TableCell>{r.avg_score}%</TableCell>
                    <TableCell>
                      <Typography variant="caption" color={r.retry_rate > 30 ? 'warning.main' : 'text.secondary'}>
                        {r.retry_rate}%
                      </Typography>
                    </TableCell>
                    <TableCell>{r.avg_score_attempt1 != null ? `${r.avg_score_attempt1}%` : '—'}</TableCell>
                    <TableCell>{r.avg_score_attempt2 != null ? `${r.avg_score_attempt2}%` : '—'}</TableCell>
                    <TableCell>{r.avg_score_attempt3 != null ? `${r.avg_score_attempt3}%` : '—'}</TableCell>
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

export default QuizReport
