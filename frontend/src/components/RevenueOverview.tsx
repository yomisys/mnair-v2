import React, { useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import { Alert, Box, Button, Grid, Paper, Stack, Typography } from '@mui/material'
import { Bar } from 'react-chartjs-2'
import { adminAPI, AdminOverview, formatNaira } from '../services/api'
import { errorText, StatCard } from './AdminKit'

/**
 * Money + sponsorship at the top of the admin dashboard: what was billed,
 * collected and is still owed, with a six-month trend and quick links to
 * the pages where the admin acts on it.
 */
const RevenueOverview: React.FC = () => {
  const [o, setO] = useState<AdminOverview | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { adminAPI.overview().then(setO).catch((e) => setError(errorText(e, 'Could not load revenue.'))) }, [])

  if (error) return <Alert severity="warning" sx={{ mb: 3 }}>{error}</Alert>
  if (!o) return null
  const r = o.revenue
  const label = (m: string) => new Date(`${m}-01T00:00:00`).toLocaleString('en-NG', { month: 'short' })
  const chart = {
    labels: o.trend.map((t) => label(t.month)),
    datasets: [
      { label: 'Billed to sponsors', data: o.trend.map((t) => t.charged_kobo / 100), backgroundColor: '#90CAF9', borderRadius: 4, maxBarThickness: 28 },
      { label: 'Collected', data: o.trend.map((t) => t.collected_kobo / 100), backgroundColor: '#2E7D32', borderRadius: 4, maxBarThickness: 28 },
    ],
  }

  return (
    <Paper elevation={0} sx={{ p: 2.5, mb: 4, border: '1px solid', borderColor: 'grey.200' }}>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} sx={{ mb: 2 }} spacing={1}>
        <Box>
          <Typography variant="h6" fontWeight={700}>Revenue & sponsorship</Typography>
          <Typography variant="body2" color="text.secondary">
            {o.sponsors.active} active sponsors · {o.learners.sponsored.toLocaleString()} sponsored learners · {r.pending_payments} payments pending
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button size="small" component={RouterLink} to="/dashboard/sponsors">Sponsors</Button>
          <Button size="small" component={RouterLink} to="/dashboard/payments">Payments</Button>
          <Button size="small" component={RouterLink} to="/dashboard/learners">Learners</Button>
        </Stack>
      </Stack>
      <Grid container spacing={2}>
        <Grid item xs={6} md={3}><StatCard label="Collected (all time)" value={formatNaira(r.total_collected_kobo)} tone="good"
          hint={`${formatNaira(r.sponsor_collected_kobo)} sponsors · ${formatNaira(r.learner_certificate_collected_kobo)} learners`} /></Grid>
        <Grid item xs={6} md={3}><StatCard label="Last 30 days" value={formatNaira(r.collected_last_30_days_kobo)} /></Grid>
        <Grid item xs={6} md={3}><StatCard label="Owed by sponsors" value={formatNaira(r.outstanding_kobo)} tone={r.outstanding_kobo ? 'bad' : 'default'}
          hint={`${o.sponsors.owing} sponsor${o.sponsors.owing === 1 ? '' : 's'} · ${formatNaira(r.sponsor_credit_kobo)} prepaid credit`} /></Grid>
        <Grid item xs={6} md={3}><StatCard label="Deposits unpaid" value={formatNaira(r.deposits_outstanding_kobo)} tone={r.deposits_outstanding_kobo ? 'warn' : 'default'}
          hint={`${formatNaira(r.charged_kobo)} billed in total`} /></Grid>
        <Grid item xs={12}>
          <Box sx={{ height: 220 }}>
            <Bar data={chart} options={{
              responsive: true, maintainAspectRatio: false,
              plugins: { legend: { position: 'bottom' as const }, tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ₦${Number(c.raw).toLocaleString('en-NG')}` } } },
              scales: { y: { beginAtZero: true, grid: { color: '#f0f0f0' }, ticks: { callback: (v) => `₦${Number(v).toLocaleString('en-NG')}` } }, x: { grid: { display: false } } },
            }} />
          </Box>
        </Grid>
      </Grid>
    </Paper>
  )
}

export default RevenueOverview
