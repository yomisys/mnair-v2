import React, { useEffect, useState } from 'react'
import {
  Box, Card, CardContent, Container, Typography, CircularProgress, Alert,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  Grid, Chip, TextField, InputAdornment, LinearProgress,
} from '@mui/material'
import { Search as SearchIcon } from '@mui/icons-material'
import { format } from 'date-fns'
import { analyticsAPI } from '../services/api'
import ExportButton from '../components/ExportButton'

const LANG_NAMES: Record<string, string> = {
  en: 'English', ha: 'Hausa', ig: 'Igbo', pid: 'Pidgin', yo: 'Yoruba',
  ENGLISH: 'English', HAUSA: 'Hausa', IGBO: 'Igbo', PIDGIN: 'Pidgin', YORUBA: 'Yoruba',
}

const LANG_COLORS: Record<string, string> = {
  ENGLISH: '#2196F3', HAUSA: '#FF9800', YORUBA: '#9C27B0', IGBO: '#F44336', PIDGIN: '#00BCD4',
  en: '#2196F3', ha: '#FF9800', yo: '#9C27B0', ig: '#F44336', pid: '#00BCD4',
}

interface UserRow {
  id: number; phone_number: string; name: string | null; language: string; role: string
  current_day: number; completed_days: number; is_active: boolean; created_at: string
  lesson_count: number; quiz_count: number; conversation_count: number
}

const UsersReport: React.FC = () => {
  const [data, setData] = useState<UserRow[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    analyticsAPI.getUsers()
      .then(setData)
      .catch(e => setError(e.response?.data?.detail || 'Failed to load'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>
  if (error) return <Container sx={{ mt: 4 }}><Alert severity="error">{error}</Alert></Container>

  const learners = data.filter(u => u.role !== 'ADMIN')
  const filtered = learners.filter(u =>
    !search || u.phone_number.includes(search) || (u.name ?? '').toLowerCase().includes(search.toLowerCase())
  )

  const activeCount = learners.filter(u => u.is_active).length
  const completedCount = learners.filter(u => u.completed_days >= 7).length
  const avgDay = learners.length ? (learners.reduce((s, u) => s + u.current_day, 0) / learners.length).toFixed(1) : '0'

  const exportRows = filtered.map(u => ({
    phone_number: u.phone_number,
    name: u.name,
    language: LANG_NAMES[u.language] ?? u.language,
    current_day: u.current_day,
    completed_days: u.completed_days,
    is_active: u.is_active,
    lessons: u.lesson_count,
    quizzes: u.quiz_count,
    sessions: u.conversation_count,
    joined: u.created_at,
  }))

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 6 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Box>
          <Typography variant="h5" fontWeight={700}>User Directory</Typography>
          <Typography variant="body2" color="text.secondary">All registered learners and their progress</Typography>
        </Box>
        <ExportButton data={exportRows as any} filename="users_report.csv" />
      </Box>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: 'Total Learners', value: learners.length, color: '#1B8A4E' },
          { label: 'Active Users', value: activeCount, color: '#4CAF50' },
          { label: 'Completed Program', value: completedCount, color: '#2196F3' },
          { label: 'Avg Current Day', value: avgDay, color: '#FF9800' },
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

      <Card>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
            <Typography variant="h6" fontWeight={600}>Learners ({filtered.length})</Typography>
            <TextField
              size="small"
              placeholder="Search by phone or name…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
              sx={{ width: 280 }}
            />
          </Box>
          <TableContainer component={Paper} elevation={0} sx={{ maxHeight: 600 }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  {['Phone Number', 'Name', 'Language', 'Day', 'Progress', 'Lessons', 'Quizzes', 'Sessions', 'Status', 'Joined'].map(h => (
                    <TableCell key={h} sx={{ fontWeight: 700, bgcolor: '#f5f6fa', whiteSpace: 'nowrap' }}>{h}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {filtered.map(u => (
                  <TableRow key={u.id} hover>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: 13 }}>{u.phone_number}</TableCell>
                    <TableCell>{u.name ?? <Typography variant="caption" color="text.secondary">—</Typography>}</TableCell>
                    <TableCell>
                      <Chip
                        label={LANG_NAMES[u.language] ?? u.language}
                        size="small"
                        sx={{ bgcolor: (LANG_COLORS[u.language] ?? '#9E9E9E') + '22', color: LANG_COLORS[u.language] ?? '#9E9E9E', fontWeight: 600, fontSize: 11 }}
                      />
                    </TableCell>
                    <TableCell>
                      <Chip label={`Day ${u.current_day}`} size="small" variant="outlined" />
                    </TableCell>
                    <TableCell sx={{ minWidth: 140 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <LinearProgress
                          variant="determinate"
                          value={Math.min((u.completed_days / 7) * 100, 100)}
                          sx={{ flex: 1, height: 6, borderRadius: 3, bgcolor: '#e0e0e0', '& .MuiLinearProgress-bar': { bgcolor: u.completed_days >= 7 ? '#4CAF50' : '#1B8A4E' } }}
                        />
                        <Typography variant="caption" color="text.secondary" sx={{ minWidth: 32 }}>
                          {u.completed_days}/7
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="center">{u.lesson_count}</TableCell>
                    <TableCell align="center">{u.quiz_count}</TableCell>
                    <TableCell align="center">{u.conversation_count}</TableCell>
                    <TableCell>
                      <Chip
                        label={u.is_active ? 'Active' : 'Inactive'}
                        size="small"
                        color={u.is_active ? 'success' : 'default'}
                      />
                    </TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap', fontSize: 12 }}>
                      {format(new Date(u.created_at), 'dd MMM yyyy')}
                    </TableCell>
                  </TableRow>
                ))}
                {filtered.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={10} align="center">
                      <Typography variant="body2" color="text.secondary" sx={{ py: 4 }}>No users found</Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    </Container>
  )
}

export default UsersReport
