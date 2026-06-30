import React, { useEffect, useState } from 'react'
import {
  Box, Card, CardContent, Container, Typography, CircularProgress,
  Alert, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Paper, Chip, MenuItem, Select, FormControl, InputLabel, LinearProgress,
  Grid,
} from '@mui/material'
import { Bar } from 'react-chartjs-2'
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend,
} from 'chart.js'
import { analyticsAPI } from '../services/api'
import ExportButton from '../components/ExportButton'

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend)

const LANG_NAMES: Record<string, string> = {
  en: 'English', ha: 'Hausa', ig: 'Igbo', pid: 'Pidgin', yo: 'Yoruba', '': 'All',
}
const TOPIC_LABELS: Record<string, string> = {
  what_is_ai: 'What is AI', how_ai_works: 'How AI Works',
  ai_in_nigeria: 'AI in Nigeria', ai_tools: 'AI Tools', ai_ethics: 'AI Ethics',
}

interface LessonRow {
  lesson_id: string; db_id: number; day: number; topic: string; language: string
  title: string; started_count: number; completed_count: number; completion_rate: number
  avg_score: number | null; avg_attempts: number; first_attempt_pass_rate: number
}

const LessonsReport: React.FC = () => {
  const [data, setData] = useState<LessonRow[]>([])
  const [lang, setLang] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    analyticsAPI.getLessons(lang || undefined)
      .then(setData)
      .catch(e => setError(e.response?.data?.detail || 'Failed to load'))
      .finally(() => setLoading(false))
  }, [lang])

  const byDay = Array.from({ length: 7 }, (_, i) => {
    const rows = data.filter(r => r.day === i + 1)
    const avg = rows.length ? rows.reduce((s, r) => s + r.completion_rate, 0) / rows.length : 0
    return Math.round(avg)
  })

  const hardest = [...data].sort((a, b) => (a.completion_rate ?? 0) - (b.completion_rate ?? 0)).slice(0, 5)

  const exportData = data.map(r => ({
    lesson_id: r.lesson_id, day: r.day, topic: r.topic, language: r.language,
    started: r.started_count, completed: r.completed_count,
    completion_rate: r.completion_rate, avg_score: r.avg_score,
    avg_attempts: r.avg_attempts, first_pass_rate: r.first_attempt_pass_rate,
  }))

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>
  if (error) return <Container sx={{ mt: 4 }}><Alert severity="error">{error}</Alert></Container>

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 6 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Box>
          <Typography variant="h5" fontWeight={700}>Lesson Performance</Typography>
          <Typography variant="body2" color="text.secondary">Completion rates and quiz scores per lesson</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Language</InputLabel>
            <Select value={lang} label="Language" onChange={e => setLang(e.target.value)}>
              {Object.entries(LANG_NAMES).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
            </Select>
          </FormControl>
          <ExportButton data={exportData as any} filename="lessons_report.csv" />
        </Box>
      </Box>

      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={7}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>Avg Completion Rate by Day</Typography>
              <Bar
                data={{
                  labels: Array.from({ length: 7 }, (_, i) => `Day ${i + 1}`),
                  datasets: [{ label: 'Completion %', data: byDay, backgroundColor: '#1B8A4E', borderRadius: 6 }],
                }}
                options={{
                  responsive: true,
                  plugins: { legend: { display: false } },
                  scales: { y: { beginAtZero: true, max: 100, ticks: { callback: v => `${v}%` } } },
                }}
              />
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={5}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>Hardest Lessons</Typography>
              <Typography variant="caption" color="text.secondary">Lowest completion rates</Typography>
              <Box sx={{ mt: 2 }}>
                {hardest.map(r => (
                  <Box key={r.lesson_id} sx={{ mb: 2 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <Typography variant="body2" noWrap sx={{ maxWidth: '70%' }}>
                        D{r.day} {TOPIC_LABELS[r.topic] ?? r.topic} ({LANG_NAMES[r.language]})
                      </Typography>
                      <Typography variant="body2" fontWeight={600} color="error.main">
                        {r.completion_rate}%
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={r.completion_rate}
                      sx={{ height: 6, borderRadius: 3, bgcolor: '#fde', '& .MuiLinearProgress-bar': { bgcolor: '#e53935' } }}
                    />
                  </Box>
                ))}
                {!hardest.length && <Typography variant="body2" color="text.secondary">No data yet</Typography>}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Card>
        <CardContent>
          <Typography variant="h6" fontWeight={600} gutterBottom>All Lessons</Typography>
          <TableContainer component={Paper} elevation={0} sx={{ maxHeight: 520 }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  {['Day', 'Topic', 'Language', 'Started', 'Completed', 'Completion', 'Avg Score', 'Avg Attempts', '1st-Pass Rate'].map(h => (
                    <TableCell key={h} sx={{ fontWeight: 700, bgcolor: '#f5f6fa' }}>{h}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {data.map(r => (
                  <TableRow key={r.lesson_id} hover>
                    <TableCell><Chip label={`Day ${r.day}`} size="small" /></TableCell>
                    <TableCell>{TOPIC_LABELS[r.topic] ?? r.topic}</TableCell>
                    <TableCell><Chip label={LANG_NAMES[r.language]} size="small" variant="outlined" /></TableCell>
                    <TableCell>{r.started_count}</TableCell>
                    <TableCell>{r.completed_count}</TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <LinearProgress
                          variant="determinate" value={r.completion_rate}
                          sx={{ width: 60, height: 6, borderRadius: 3, bgcolor: '#e0e0e0', '& .MuiLinearProgress-bar': { bgcolor: r.completion_rate >= 70 ? '#4CAF50' : r.completion_rate >= 40 ? '#FF9800' : '#f44336' } }}
                        />
                        <Typography variant="caption">{r.completion_rate}%</Typography>
                      </Box>
                    </TableCell>
                    <TableCell>{r.avg_score != null ? `${r.avg_score}%` : '—'}</TableCell>
                    <TableCell>{r.avg_attempts.toFixed(1)}</TableCell>
                    <TableCell>{r.first_attempt_pass_rate}%</TableCell>
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

export default LessonsReport
