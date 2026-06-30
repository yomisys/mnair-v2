import React, { useEffect, useState } from 'react'
import {
  Box, Card, CardContent, Container, Typography, CircularProgress, Alert,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  Grid, Chip,
} from '@mui/material'
import { Bar, Doughnut } from 'react-chartjs-2'
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, ArcElement,
  Title, Tooltip, Legend,
} from 'chart.js'
import { format } from 'date-fns'
import { analyticsAPI } from '../services/api'
import ExportButton from '../components/ExportButton'

ChartJS.register(CategoryScale, LinearScale, BarElement, ArcElement, Title, Tooltip, Legend)

interface EmployerRow {
  id: number; company_name: string; industry: string | null; location: string | null
  company_size: string | null; certificates_verified: number; api_requests: number
  is_active: boolean; is_approved: boolean; is_verified: boolean
  created_at: string; last_verification_at: string | null
}

const EmployersReport: React.FC = () => {
  const [data, setData] = useState<EmployerRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    analyticsAPI.getEmployers()
      .then(setData)
      .catch(e => setError(e.response?.data?.detail || 'Failed to load'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>
  if (error) return <Container sx={{ mt: 4 }}><Alert severity="error">{error}</Alert></Container>

  // Industry breakdown
  const industryMap: Record<string, number> = {}
  data.forEach(e => { const k = e.industry || 'Unknown'; industryMap[k] = (industryMap[k] || 0) + 1 })
  const topIndustries = Object.entries(industryMap).sort((a, b) => b[1] - a[1]).slice(0, 8)
  const COLORS = ['#1B8A4E', '#4CAF50', '#81C784', '#2196F3', '#FF9800', '#9C27B0', '#F44336', '#00BCD4']

  const industryChart = {
    labels: topIndustries.map(([k]) => k),
    datasets: [{ data: topIndustries.map(([, v]) => v), backgroundColor: COLORS, borderWidth: 2, borderColor: '#fff' }],
  }

  const top10 = data.slice(0, 10)
  const barChart = {
    labels: top10.map(e => e.company_name.length > 20 ? e.company_name.slice(0, 20) + '…' : e.company_name),
    datasets: [{
      label: 'Certificates Verified',
      data: top10.map(e => e.certificates_verified),
      backgroundColor: '#1B8A4E',
      borderRadius: 6,
    }],
  }

  const exportData = data.map(e => ({
    company_name: e.company_name, industry: e.industry, location: e.location,
    company_size: e.company_size, certificates_verified: e.certificates_verified,
    api_requests: e.api_requests, is_active: e.is_active, is_approved: e.is_approved,
    is_verified: e.is_verified, created_at: e.created_at,
    last_verification_at: e.last_verification_at,
  }))

  const approved = data.filter(e => e.is_approved).length
  const pending = data.filter(e => e.is_verified && !e.is_approved).length
  const totalVerifications = data.reduce((s, e) => s + e.certificates_verified, 0)

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 6 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Box>
          <Typography variant="h5" fontWeight={700}>Employer Intelligence</Typography>
          <Typography variant="body2" color="text.secondary">Companies verifying MNAIR certificates</Typography>
        </Box>
        <ExportButton data={exportData as any} filename="employers_report.csv" />
      </Box>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: 'Total Employers', value: data.length, color: '#1B8A4E' },
          { label: 'Approved', value: approved, color: '#4CAF50' },
          { label: 'Pending Approval', value: pending, color: '#FF9800' },
          { label: 'Total Verifications', value: totalVerifications.toLocaleString(), color: '#2196F3' },
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
              <Typography variant="h6" fontWeight={600} gutterBottom>Top 10 by Verifications</Typography>
              {top10.every(e => e.certificates_verified === 0) ? (
                <Typography variant="body2" color="text.secondary">No verifications yet</Typography>
              ) : (
                <Bar
                  data={barChart}
                  options={{
                    indexAxis: 'y' as const,
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: { x: { beginAtZero: true } },
                  }}
                />
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={5}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>Industry Distribution</Typography>
              {topIndustries.length === 0 ? (
                <Typography variant="body2" color="text.secondary">No data yet</Typography>
              ) : (
                <Doughnut
                  data={industryChart}
                  options={{ plugins: { legend: { position: 'bottom', labels: { padding: 10, font: { size: 11 } } } }, cutout: '55%' }}
                />
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Card>
        <CardContent>
          <Typography variant="h6" fontWeight={600} gutterBottom>All Employers</Typography>
          <TableContainer component={Paper} elevation={0} sx={{ maxHeight: 520 }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  {['Company', 'Industry', 'Location', 'Size', 'Verifications', 'API Requests', 'Status', 'Last Active'].map(h => (
                    <TableCell key={h} sx={{ fontWeight: 700, bgcolor: '#f5f6fa' }}>{h}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {data.map(e => (
                  <TableRow key={e.id} hover>
                    <TableCell><strong>{e.company_name}</strong></TableCell>
                    <TableCell>{e.industry ?? '—'}</TableCell>
                    <TableCell>{e.location ?? '—'}</TableCell>
                    <TableCell>{e.company_size ?? '—'}</TableCell>
                    <TableCell>
                      <Typography variant="body2" fontWeight={600} color={e.certificates_verified > 0 ? 'success.main' : 'text.secondary'}>
                        {e.certificates_verified}
                      </Typography>
                    </TableCell>
                    <TableCell>{e.api_requests}</TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                        {e.is_approved && <Chip label="Approved" size="small" color="success" />}
                        {e.is_verified && !e.is_approved && <Chip label="Pending" size="small" color="warning" />}
                        {!e.is_verified && <Chip label="Unverified" size="small" color="default" />}
                        {!e.is_active && <Chip label="Inactive" size="small" color="error" />}
                      </Box>
                    </TableCell>
                    <TableCell>
                      {e.last_verification_at
                        ? format(new Date(e.last_verification_at), 'dd MMM yyyy')
                        : '—'}
                    </TableCell>
                  </TableRow>
                ))}
                {data.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={8} align="center">
                      <Typography variant="body2" color="text.secondary" sx={{ py: 4 }}>No employers registered yet</Typography>
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

export default EmployersReport
