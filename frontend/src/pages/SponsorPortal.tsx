import React, { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Grid,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import {
  formatNaira,
  sponsorAPI,
  SponsorDashboard,
  SponsorLearner,
  SponsorStatement,
  SPONSOR_TOKEN_KEY,
} from '../services/api'
import { CertificateActions } from '../components/AdminKit'

/**
 * Sponsor portal — what a church, company or state sees: how many of its
 * people enrolled and certified, its codes and join links, the monthly
 * statement and a pay button. Names and progress only; never phone numbers.
 */

const errorText = (e: unknown, fallback: string): string => {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

const Stat: React.FC<{ label: string; value: React.ReactNode; hint?: string }> = ({ label, value, hint }) => (
  <Paper elevation={0} sx={{ p: 2.5, border: '1px solid', borderColor: 'grey.200', borderRadius: 2, height: '100%' }}>
    <Typography variant="body2" color="text.secondary">{label}</Typography>
    <Typography variant="h4" fontWeight={800} sx={{ mt: 0.5 }}>{value}</Typography>
    {hint && <Typography variant="caption" color="text.secondary">{hint}</Typography>}
  </Paper>
)

const LoginPanel: React.FC<{ onDone: () => void }> = ({ onDone }) => {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const r = await sponsorAPI.login(email, password)
      localStorage.setItem(SPONSOR_TOKEN_KEY, r.access_token)
      onDone()
    } catch (err) {
      setError(errorText(err, 'Sign-in failed.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Container maxWidth="xs" sx={{ py: 6 }}>
      <Paper elevation={0} sx={{ p: 3, border: '1px solid', borderColor: 'grey.200', borderRadius: 3 }}>
        <Typography variant="h5" fontWeight={800}>Sponsor dashboard</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Sign in with the email and password MNAIR set up for your organisation.
        </Typography>
        <Box component="form" onSubmit={submit}>
          <Stack spacing={2}>
            <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required fullWidth />
            <TextField label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required fullWidth />
            {error && <Alert severity="error">{error}</Alert>}
            <Button type="submit" variant="contained" size="large" disabled={busy}>
              {busy ? <CircularProgress size={22} color="inherit" /> : 'Sign in'}
            </Button>
          </Stack>
        </Box>
      </Paper>
    </Container>
  )
}

const recentMonths = (n: number) => {
  const out: { year: number; month: number; label: string }[] = []
  const d = new Date()
  for (let i = 0; i < n; i++) {
    const m = new Date(d.getFullYear(), d.getMonth() - i, 1)
    out.push({ year: m.getFullYear(), month: m.getMonth() + 1, label: m.toLocaleString('en-NG', { month: 'long', year: 'numeric' }) })
  }
  return out
}

const SponsorPortal: React.FC = () => {
  const [authed, setAuthed] = useState(() => !!localStorage.getItem(SPONSOR_TOKEN_KEY))
  const [dash, setDash] = useState<SponsorDashboard | null>(null)
  const [learners, setLearners] = useState<SponsorLearner[]>([])
  const [learnerTotal, setLearnerTotal] = useState(0)
  const [page, setPage] = useState(0)
  const months = recentMonths(12)
  const [period, setPeriod] = useState(`${months[0].year}-${months[0].month}`)
  const [statement, setStatement] = useState<SponsorStatement | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [paying, setPaying] = useState(false)
  const PAGE = 50

  const handleAuthError = useCallback((e: unknown) => {
    const status = (e as { response?: { status?: number } })?.response?.status
    if (status === 401 || status === 403) {
      localStorage.removeItem(SPONSOR_TOKEN_KEY)
      setAuthed(false)
      return true
    }
    return false
  }, [])

  const load = useCallback(async () => {
    try {
      setDash(await sponsorAPI.dashboard())
    } catch (e) {
      if (!handleAuthError(e)) setError(errorText(e, 'Could not load your dashboard.'))
    }
  }, [handleAuthError])

  useEffect(() => { if (authed) load() }, [authed, load])

  useEffect(() => {
    if (!authed) return
    sponsorAPI.learners(page * PAGE, PAGE)
      .then((r) => { setLearners(r.items); setLearnerTotal(r.total) })
      .catch((e) => { if (!handleAuthError(e)) setError(errorText(e, 'Could not load learners.')) })
  }, [authed, page, handleAuthError])

  useEffect(() => {
    if (!authed) return
    const [y, m] = period.split('-').map(Number)
    sponsorAPI.statement(y, m).then(setStatement).catch((e) => { if (!handleAuthError(e)) setStatement(null) })
  }, [authed, period, handleAuthError])

  const pay = async (purpose: 'deposit' | 'balance') => {
    setPaying(true)
    setError(null)
    try {
      const r = await sponsorAPI.pay(purpose)
      window.location.href = r.authorization_url
    } catch (e) {
      setError(errorText(e, 'Could not start the payment.'))
      setPaying(false)
    }
  }

  const downloadCsv = async () => {
    try {
      const blob = await sponsorAPI.learnersCsv()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'mnair-learners.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(errorText(e, 'Could not download the list.'))
    }
  }

  const signOut = () => {
    localStorage.removeItem(SPONSOR_TOKEN_KEY)
    setDash(null)
    setAuthed(false)
  }

  if (!authed) return <LoginPanel onDone={() => setAuthed(true)} />
  if (!dash) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 10 }}>
        {error ? <Alert severity="error">{error}</Alert> : <CircularProgress />}
      </Box>
    )
  }

  const { organization: org, learners: l, account } = dash
  const maxDay = Math.max(1, ...Object.values(l.days_completed))

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 3 }} flexWrap="wrap" gap={1}>
        <Box>
          <Typography variant="h4" fontWeight={800}>{org.name}</Typography>
          <Typography color="text.secondary">
            {org.package.charAt(0).toUpperCase() + org.package.slice(1)} package · {formatNaira(org.price_per_certificate_kobo)} per certified learner
            {org.learner_cap ? ` · up to ${org.learner_cap.toLocaleString()} learners` : ''}
          </Typography>
        </Box>
        <Button onClick={signOut}>Sign out</Button>
      </Stack>

      {error && <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>{error}</Alert>}

      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={6} md={3}><Stat label="Enrolled" value={l.enrolled.toLocaleString()} /></Grid>
        <Grid item xs={6} md={3}><Stat label="Active this week" value={l.active_last_7_days.toLocaleString()} /></Grid>
        <Grid item xs={6} md={3}><Stat label="Certified" value={l.certified.toLocaleString()} hint={`${l.completion_rate}% of enrolled`} /></Grid>
        <Grid item xs={6} md={3}>
          <Stat label="Average quiz score" value={l.average_quiz_score != null ? `${l.average_quiz_score}%` : '–'} />
        </Grid>
      </Grid>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} md={6}>
          <Paper elevation={0} sx={{ p: 2.5, border: '1px solid', borderColor: 'grey.200', borderRadius: 2, height: '100%' }}>
            <Typography fontWeight={700} sx={{ mb: 1.5 }}>Where your learners are</Typography>
            {Array.from({ length: 8 }, (_, d) => (
              <Stack key={d} direction="row" alignItems="center" spacing={1.5} sx={{ mb: 0.75 }}>
                <Typography variant="body2" sx={{ width: 110 }}>{d === 0 ? 'Not started' : d === 7 ? 'Finished' : `Done day ${d}`}</Typography>
                <LinearProgress
                  variant="determinate"
                  value={(100 * (l.days_completed[String(d)] || 0)) / maxDay}
                  sx={{ flex: 1, height: 10, borderRadius: 5 }}
                  color={d === 7 ? 'success' : 'primary'}
                />
                <Typography variant="body2" sx={{ width: 48, textAlign: 'right' }}>{l.days_completed[String(d)] || 0}</Typography>
              </Stack>
            ))}
          </Paper>
        </Grid>
        <Grid item xs={12} md={6}>
          <Paper elevation={0} sx={{ p: 2.5, border: '1px solid', borderColor: 'grey.200', borderRadius: 2, height: '100%' }}>
            <Typography fontWeight={700} sx={{ mb: 1.5 }}>Account</Typography>
            <Table size="small">
              <TableBody>
                <TableRow><TableCell>Certificates billed</TableCell><TableCell align="right">{account.certificates_billed.toLocaleString()}</TableCell></TableRow>
                <TableRow><TableCell>Total charged</TableCell><TableCell align="right">{formatNaira(account.charged_kobo)}</TableCell></TableRow>
                <TableRow><TableCell>Total paid</TableCell><TableCell align="right">{formatNaira(account.paid_kobo)}</TableCell></TableRow>
                <TableRow><TableCell>Deposit credit left</TableCell><TableCell align="right">{formatNaira(account.credit_remaining_kobo)}</TableCell></TableRow>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700 }}>Amount due</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>{formatNaira(account.amount_due_kobo)}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
            <Stack direction="row" spacing={1} sx={{ mt: 2 }} flexWrap="wrap" gap={1}>
              {account.deposit_outstanding_kobo > 0 && (
                <Button variant="contained" disabled={paying || !dash.payments_enabled} onClick={() => pay('deposit')}>
                  Pay deposit {formatNaira(account.deposit_outstanding_kobo)}
                </Button>
              )}
              {account.amount_due_kobo > 0 && (
                <Button variant="contained" color="success" disabled={paying || !dash.payments_enabled} onClick={() => pay('balance')}>
                  Pay {formatNaira(account.amount_due_kobo)}
                </Button>
              )}
            </Stack>
            {!dash.payments_enabled && (
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                Online payment is not switched on yet. Contact MNAIR for bank transfer details.
              </Typography>
            )}
          </Paper>
        </Grid>
      </Grid>

      <Paper elevation={0} sx={{ p: 2.5, border: '1px solid', borderColor: 'grey.200', borderRadius: 2, mb: 3 }}>
        <Typography fontWeight={700} sx={{ mb: 1.5 }}>Your codes and join links</Typography>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Code</TableCell><TableCell>Label</TableCell><TableCell align="right">Enrolled</TableCell>
              <TableCell>Web link</TableCell><TableCell>Telegram link</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {dash.codes.map((c) => (
              <TableRow key={c.code}>
                <TableCell>
                  <strong>{c.code}</strong>{!c.is_active && <Chip size="small" label="inactive" sx={{ ml: 1 }} />}
                </TableCell>
                <TableCell>{c.label || '–'}</TableCell>
                <TableCell align="right">{c.enrolled}{c.max_enrolments ? ` / ${c.max_enrolments}` : ''}</TableCell>
                <TableCell><Button size="small" onClick={() => navigator.clipboard?.writeText(c.join_url)}>Copy</Button></TableCell>
                <TableCell>
                  {c.telegram_url ? <Button size="small" onClick={() => navigator.clipboard?.writeText(c.telegram_url!)}>Copy</Button> : '–'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>

      <Paper elevation={0} sx={{ p: 2.5, border: '1px solid', borderColor: 'grey.200', borderRadius: 2, mb: 3 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }} flexWrap="wrap" gap={1}>
          <Typography fontWeight={700}>Monthly statement</Typography>
          <TextField select size="small" value={period} onChange={(e) => setPeriod(e.target.value)}>
            {months.map((m) => <MenuItem key={`${m.year}-${m.month}`} value={`${m.year}-${m.month}`}>{m.label}</MenuItem>)}
          </TextField>
        </Stack>
        {statement && (
          <Table size="small">
            <TableBody>
              <TableRow>
                <TableCell>Opening balance</TableCell>
                <TableCell align="right">{formatNaira(statement.opening_balance_kobo)}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Certificates issued ({statement.certificates_issued} × {formatNaira(statement.price_per_certificate_kobo)})</TableCell>
                <TableCell align="right">{formatNaira(statement.charges_kobo)}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Payments received</TableCell>
                <TableCell align="right">−{formatNaira(statement.payments_kobo)}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{ fontWeight: 700 }}>
                  {statement.closing_balance_kobo < 0 ? 'Closing credit' : 'Closing balance'}
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 700 }}>{formatNaira(Math.abs(statement.closing_balance_kobo))}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        )}
      </Paper>

      <Paper elevation={0} sx={{ p: 2.5, border: '1px solid', borderColor: 'grey.200', borderRadius: 2 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
          <Typography fontWeight={700}>Learners ({learnerTotal.toLocaleString()})</Typography>
          <Button size="small" variant="outlined" onClick={downloadCsv}>Download CSV</Button>
        </Stack>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell><TableCell>Language</TableCell><TableCell align="right">Days done</TableCell>
                <TableCell>Certificate</TableCell><TableCell>Joined</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {learners.map((x, i) => (
                <TableRow key={i}>
                  <TableCell>{x.name}</TableCell>
                  <TableCell>{x.language.toUpperCase()}</TableCell>
                  <TableCell align="right">{x.completed_days}/7</TableCell>
                  <TableCell>
                    {x.certified && x.certificate_id ? (
                      <Stack direction="row" alignItems="center" spacing={0.5}>
                        <Chip size="small" color="success" label={x.certificate_id} />
                        <CertificateActions compact certificateId={x.certificate_id}
                          fetchPdf={sponsorAPI.certificatePdf} makeLink={(cid, days) => sponsorAPI.certificateLink(cid, days)} />
                      </Stack>
                    ) : '–'}
                  </TableCell>
                  <TableCell>{x.joined_at ? new Date(x.joined_at).toLocaleDateString('en-NG') : '–'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
        {learnerTotal > PAGE && (
          <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ mt: 1.5 }}>
            <Button size="small" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
            <Button size="small" disabled={(page + 1) * PAGE >= learnerTotal} onClick={() => setPage(page + 1)}>Next</Button>
          </Stack>
        )}
      </Paper>
    </Container>
  )
}

export default SponsorPortal
