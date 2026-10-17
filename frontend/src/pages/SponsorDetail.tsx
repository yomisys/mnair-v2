import React, { useEffect, useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'
import {
  Alert, Box, Breadcrumbs, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, Grid, IconButton,
  LinearProgress, Link, MenuItem, Paper, Stack, Switch, Tab, Table, TableBody, TableCell, TableHead, TablePagination,
  TableRow, Tabs, TextField, Tooltip, Typography,
} from '@mui/material'
import { ContentCopy as CopyIcon } from '@mui/icons-material'
import { adminAPI, AdminPayment, formatNaira, saveBlob, SponsorBranding, SponsorStatement } from '../services/api'
import { SponsorAdvertCard } from '../components/SponsorBrand'
import {
  CertificateActions, copyText, errorText, fmtDate, Loading, nairaToKobo, PageHeader, StatCard, StatusChip, useConfirm, useNotice,
} from '../components/AdminKit'
import { PACKAGES } from './SponsorsAdmin'

/**
 * Admin: one sponsor, end to end — account and progress, codes (add, cap,
 * expiry, switch off), learners with certificate download/share, payments
 * (Paystack links, record or void a transfer), monthly statement, and
 * settings (edit, prices, portal login, logo, advert moderation, deactivate).
 */

interface Code {
  id: number; code: string; label: string | null; max_enrolments: number | null; expires_at: string | null
  is_active: boolean; join_url: string; telegram_url: string | null; enrolled: number
}
interface Detail {
  organization: {
    id: number; name: string; package: string; price_per_certificate_kobo: number; deposit_kobo: number
    learner_cap: number | null; has_logo: boolean; is_active: boolean; contact_name: string | null; contact_email: string
    contact_phone: string | null; portal_email: string | null; has_portal_password: boolean; notes: string | null; created_at: string | null
  }
  learners: {
    enrolled: number; active_last_7_days: number; certified: number; completion_rate: number
    average_quiz_score: number | null; days_completed: Record<string, number>; by_language: Record<string, number>
  }
  codes: Code[]
  account: {
    certificates_billed: number; charged_kobo: number; paid_kobo: number; deposit_paid_kobo: number
    deposit_outstanding_kobo: number; credit_remaining_kobo: number; amount_due_kobo: number
  }
  branding: SponsorBranding
  payments_enabled: boolean
}
interface LearnerItem {
  user_id: number; name: string; language: string; completed_days: number; certified: boolean; is_active: boolean
  any_certificate_id: string | null; certificate_access: string | null; joined_at: string | null; last_active_at: string | null
}

const card = { p: 2, border: '1px solid', borderColor: 'grey.200' } as const

const Copyable: React.FC<{ text: string }> = ({ text }) => {
  const [done, setDone] = useState(false)
  return (
    <Tooltip title={done ? 'Copied' : 'Copy'}>
      <IconButton size="small" onClick={async (e) => { e.stopPropagation(); setDone(await copyText(text)) }}><CopyIcon fontSize="inherit" /></IconButton>
    </Tooltip>
  )
}

const months = () => {
  const out: { y: number; m: number; label: string }[] = []
  const d = new Date()
  for (let i = 0; i < 12; i++) {
    const x = new Date(d.getFullYear(), d.getMonth() - i, 1)
    out.push({ y: x.getFullYear(), m: x.getMonth() + 1, label: x.toLocaleString('en-NG', { month: 'long', year: 'numeric' }) })
  }
  return out
}

const SponsorDetail: React.FC = () => {
  const id = Number(useParams().id)
  const [tab, setTab] = useState(0)
  const [data, setData] = useState<Detail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { confirm, confirmDialog } = useConfirm()
  const { ok, fail, notice } = useNotice()

  const load = () => adminAPI.sponsor(id).then((d) => { setData(d); setError(null) }).catch((e) => setError(errorText(e, 'Could not load this sponsor.')))
  useEffect(() => { load() }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <Box sx={{ p: 3 }}><Alert severity="error">{error}</Alert></Box>
  if (!data) return <Loading />
  const o = data.organization
  const a = data.account

  const run = async (fn: () => Promise<unknown>, success: string) => {
    try { await fn(); ok(success); load(); return true } catch (e) { fail(errorText(e, 'That did not work.')); return false }
  }

  const toggleActive = async () => {
    if (!(await confirm({
      title: o.is_active ? `Deactivate ${o.name}?` : `Reactivate ${o.name}?`,
      body: o.is_active
        ? 'Their codes stop accepting new learners and the sponsor can no longer sign in to their portal. Learners already enrolled keep learning, and their certificates are still billed.'
        : 'Codes accept learners again and the portal login works.',
      confirmLabel: o.is_active ? 'Deactivate' : 'Reactivate', danger: o.is_active,
    }))) return
    run(() => adminAPI.updateSponsor(id, { is_active: !o.is_active }), o.is_active ? 'Sponsor deactivated.' : 'Sponsor reactivated.')
  }

  return (
    <Box sx={{ p: 3 }}>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/dashboard/sponsors" underline="hover">Sponsors</Link>
        <Typography color="text.primary">{o.name}</Typography>
      </Breadcrumbs>
      <PageHeader
        title={o.name}
        subtitle={`${o.package} · ${formatNaira(o.price_per_certificate_kobo)} per certificate · since ${fmtDate(o.created_at)}`}
        actions={<>
          {!o.is_active && <Chip color="default" label="Inactive" />}
          <Button variant="outlined" color={o.is_active ? 'error' : 'success'} onClick={toggleActive}>{o.is_active ? 'Deactivate' : 'Reactivate'}</Button>
        </>}
      />

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><StatCard label="Enrolled" value={data.learners.enrolled.toLocaleString()}
          hint={o.learner_cap ? `cap ${o.learner_cap.toLocaleString()}` : `${data.learners.active_last_7_days} active this week`} /></Grid>
        <Grid item xs={6} md={3}><StatCard label="Certified (billed)" value={a.certificates_billed.toLocaleString()} hint={`${data.learners.completion_rate}% of enrolled`} /></Grid>
        <Grid item xs={6} md={3}><StatCard label="Billed / paid" value={formatNaira(a.charged_kobo)} hint={`${formatNaira(a.paid_kobo)} paid`} /></Grid>
        <Grid item xs={6} md={3}><StatCard
          label={a.amount_due_kobo ? 'Amount due' : 'Credit remaining'}
          value={formatNaira(a.amount_due_kobo || a.credit_remaining_kobo)}
          hint={a.deposit_outstanding_kobo ? `Deposit ${formatNaira(a.deposit_outstanding_kobo)} unpaid` : 'Deposit paid'}
          tone={a.amount_due_kobo ? 'bad' : 'good'} /></Grid>
      </Grid>

      <Paper elevation={0} sx={{ ...card, p: 0 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" sx={{ borderBottom: '1px solid', borderColor: 'grey.200', px: 1 }}>
          <Tab label="Overview" /><Tab label={`Codes (${data.codes.length})`} /><Tab label="Learners" />
          <Tab label="Payments" /><Tab label="Statement" /><Tab label="Settings" />
        </Tabs>
        <Box sx={{ p: 2 }}>
          {tab === 0 && <OverviewTab data={data} />}
          {tab === 1 && <CodesTab sponsorId={id} codes={data.codes} run={run} />}
          {tab === 2 && <LearnersTab sponsorId={id} name={o.name} onError={fail} />}
          {tab === 3 && <PaymentsTab sponsorId={id} data={data} run={run} confirm={confirm} ok={ok} fail={fail} />}
          {tab === 4 && <StatementTab sponsorId={id} />}
          {tab === 5 && <SettingsTab data={data} run={run} />}
        </Box>
      </Paper>
      {confirmDialog}
      {notice}
    </Box>
  )
}

// ---------------------------------------------------------------------------

const OverviewTab: React.FC<{ data: Detail }> = ({ data }) => {
  const l = data.learners
  const max = Math.max(1, ...Object.values(l.days_completed))
  return (
    <Grid container spacing={3}>
      <Grid item xs={12} md={6}>
        <Typography fontWeight={700} sx={{ mb: 1 }}>Where learners are (days completed)</Typography>
        {Object.entries(l.days_completed).map(([d, n]) => (
          <Stack key={d} direction="row" alignItems="center" spacing={1.5} sx={{ mb: 0.75 }}>
            <Typography variant="body2" sx={{ width: 56 }}>{d === '7' ? 'Done' : `Day ${d}`}</Typography>
            <LinearProgress variant="determinate" value={(n / max) * 100} sx={{ flex: 1, height: 10, borderRadius: 5 }} color={d === '7' ? 'success' : 'primary'} />
            <Typography variant="body2" sx={{ width: 48, textAlign: 'right' }}>{n}</Typography>
          </Stack>
        ))}
      </Grid>
      <Grid item xs={12} md={6}>
        <Typography fontWeight={700} sx={{ mb: 1 }}>Languages</Typography>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
          {Object.entries(l.by_language).length === 0 && <Typography variant="body2" color="text.secondary">No learners yet.</Typography>}
          {Object.entries(l.by_language).map(([k, n]) => <Chip key={k} label={`${k.toUpperCase()} · ${n}`} />)}
        </Stack>
        <Typography fontWeight={700} sx={{ mb: 1 }}>Quality</Typography>
        <Typography variant="body2">Average quiz score of certified learners: <b>{l.average_quiz_score != null ? `${l.average_quiz_score}%` : '–'}</b></Typography>
        <Typography variant="body2">Active in the last 7 days: <b>{l.active_last_7_days}</b></Typography>
      </Grid>
    </Grid>
  )
}

// ---------------------------------------------------------------------------

type Run = (fn: () => Promise<unknown>, success: string) => Promise<boolean>

const CodesTab: React.FC<{ sponsorId: number; codes: Code[]; run: Run }> = ({ sponsorId, codes, run }) => {
  const [form, setForm] = useState<{ id?: number; code: string; label: string; max: string; expires: string } | null>(null)
  const save = async () => {
    if (!form) return
    const body: Record<string, unknown> = {
      label: form.label || null,
      max_enrolments: form.max ? Number(form.max) : null,
      expires_at: form.expires ? `${form.expires}T23:59:59` : null,
    }
    if (!form.id && form.code) body.code = form.code
    const done = await run(
      () => form.id ? adminAPI.updateCode(form.id, body) : adminAPI.createCode(sponsorId, body),
      form.id ? 'Code updated.' : 'Code created.',
    )
    if (done) setForm(null)
  }
  return (
    <>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
        <Typography variant="body2" color="text.secondary">Learners enter a code (or open its link) to be sponsored. Use one code per branch or campaign to compare them.</Typography>
        <Button variant="contained" onClick={() => setForm({ code: '', label: '', max: '', expires: '' })}>Add code</Button>
      </Stack>
      <Box sx={{ overflowX: 'auto' }}>
        <Table size="small">
          <TableHead><TableRow><TableCell>Code</TableCell><TableCell>Label</TableCell><TableCell align="right">Enrolled</TableCell><TableCell>Limits</TableCell><TableCell>Links</TableCell><TableCell>Active</TableCell><TableCell /></TableRow></TableHead>
          <TableBody>
            {codes.map((c) => {
              const expired = !!c.expires_at && new Date(c.expires_at) < new Date()
              return (
                <TableRow key={c.id}>
                  <TableCell><strong>{c.code}</strong><Copyable text={c.code} /></TableCell>
                  <TableCell>{c.label || '–'}</TableCell>
                  <TableCell align="right">{c.enrolled}{c.max_enrolments ? ` / ${c.max_enrolments}` : ''}</TableCell>
                  <TableCell>
                    <Typography variant="caption" display="block">{c.max_enrolments ? `max ${c.max_enrolments}` : 'no cap'}</Typography>
                    <Typography variant="caption" display="block" color={expired ? 'error.main' : 'text.secondary'}>
                      {c.expires_at ? `${expired ? 'expired' : 'expires'} ${fmtDate(c.expires_at)}` : 'no expiry'}
                    </Typography>
                  </TableCell>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                    <Typography variant="caption">Web</Typography><Copyable text={c.join_url} />
                    {c.telegram_url && <><Typography variant="caption">Telegram</Typography><Copyable text={c.telegram_url} /></>}
                  </TableCell>
                  <TableCell>
                    <Switch size="small" checked={c.is_active}
                      onChange={() => run(() => adminAPI.updateCode(c.id, { is_active: !c.is_active }), c.is_active ? `${c.code} switched off.` : `${c.code} switched on.`)} />
                  </TableCell>
                  <TableCell>
                    <Button size="small" onClick={() => setForm({
                      id: c.id, code: c.code, label: c.label || '', max: c.max_enrolments ? String(c.max_enrolments) : '',
                      expires: c.expires_at ? c.expires_at.slice(0, 10) : '',
                    })}>Edit</Button>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </Box>
      <Dialog open={!!form} onClose={() => setForm(null)} fullWidth maxWidth="xs">
        <DialogTitle>{form?.id ? `Edit ${form.code}` : 'New code'}</DialogTitle>
        <DialogContent>
          {form && (
            <Stack spacing={2} sx={{ mt: 1 }}>
              {!form.id && <TextField label="Code (optional)" placeholder="Generated if blank" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} />}
              <TextField label="Label" placeholder="e.g. Youth church, Ikeja" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
              <TextField label="Max learners (optional)" value={form.max} onChange={(e) => setForm({ ...form, max: e.target.value.replace(/\D/g, '') })} />
              <TextField type="date" label="Expires (optional)" value={form.expires} onChange={(e) => setForm({ ...form, expires: e.target.value })} InputLabelProps={{ shrink: true }} />
            </Stack>
          )}
        </DialogContent>
        <DialogActions><Button onClick={() => setForm(null)}>Cancel</Button><Button variant="contained" onClick={save}>Save</Button></DialogActions>
      </Dialog>
    </>
  )
}

// ---------------------------------------------------------------------------

const LearnersTab: React.FC<{ sponsorId: number; name: string; onError: (m: string) => void }> = ({ sponsorId, name, onError }) => {
  const [page, setPage] = useState(0)
  const [rows, setRows] = useState<LearnerItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    setLoading(true)
    adminAPI.sponsorLearners(sponsorId, page * 25, 25)
      .then((r) => { setRows(r.items); setTotal(r.total) })
      .catch((e) => onError(errorText(e, 'Could not load learners.')))
      .finally(() => setLoading(false))
  }, [sponsorId, page]) // eslint-disable-line react-hooks/exhaustive-deps

  const csv = async () => {
    try { saveBlob(await adminAPI.sponsorLearnersCsv(sponsorId), `${name.replace(/\W+/g, '-')}-learners.csv`) } catch (e) { onError(errorText(e, 'Export failed.')) }
  }
  return (
    <>
      <Stack direction="row" justifyContent="space-between" sx={{ mb: 1.5 }}>
        <Typography variant="body2" color="text.secondary">{total.toLocaleString()} learners. Click a name to manage the learner.</Typography>
        <Stack direction="row" spacing={1}>
          <Button component={RouterLink} to={`/dashboard/learners?sponsor_id=${sponsorId}`} size="small">Search these learners</Button>
          <Button variant="outlined" size="small" onClick={csv}>Export CSV</Button>
        </Stack>
      </Stack>
      {loading && <LinearProgress />}
      <Box sx={{ overflowX: 'auto' }}>
        <Table size="small">
          <TableHead><TableRow><TableCell>Name</TableCell><TableCell>Lang</TableCell><TableCell align="right">Days</TableCell><TableCell>Joined</TableCell><TableCell>Last active</TableCell><TableCell>Certificate</TableCell></TableRow></TableHead>
          <TableBody>
            {!loading && rows.length === 0 && <TableRow><TableCell colSpan={6} align="center" sx={{ py: 4, color: 'text.secondary' }}>No learners have used this sponsor's codes yet.</TableCell></TableRow>}
            {rows.map((r) => (
              <TableRow key={r.user_id} hover>
                <TableCell>
                  <Link component={RouterLink} to={`/dashboard/learners/${r.user_id}`}>{r.name}</Link>
                  {!r.is_active && <Box component="span" sx={{ ml: 1 }}><StatusChip status="inactive" /></Box>}
                </TableCell>
                <TableCell>{r.language.toUpperCase()}</TableCell>
                <TableCell align="right">{r.completed_days}/7</TableCell>
                <TableCell>{fmtDate(r.joined_at)}</TableCell>
                <TableCell>{fmtDate(r.last_active_at)}</TableCell>
                <TableCell>
                  {r.any_certificate_id ? (
                    <Stack direction="row" alignItems="center" spacing={1}>
                      <StatusChip status={r.certificate_access || 'free'} />
                      <CertificateActions compact certificateId={r.any_certificate_id} unpaid={r.certificate_access === 'pending_payment'}
                        fetchPdf={adminAPI.certificatePdf} makeLink={(cid, d, al) => adminAPI.certificateLink(cid, d, al)} />
                    </Stack>
                  ) : '–'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>
      <TablePagination component="div" count={total} page={page} rowsPerPage={25} rowsPerPageOptions={[25]} onPageChange={(_, p) => setPage(p)} />
    </>
  )
}

// ---------------------------------------------------------------------------

const PaymentsTab: React.FC<{
  sponsorId: number; data: Detail; run: Run
  confirm: ReturnType<typeof useConfirm>['confirm']; ok: (m: string) => void; fail: (m: string) => void
}> = ({ sponsorId, data, run, confirm, ok, fail }) => {
  const [rows, setRows] = useState<AdminPayment[]>([])
  const [transfer, setTransfer] = useState({ amount: '', note: '', date: '' })
  const [linkAmount, setLinkAmount] = useState('')
  const [lastLink, setLastLink] = useState<string | null>(null)
  const a = data.account
  const loadRows = () => adminAPI.sponsorPayments(sponsorId).then(setRows).catch((e) => fail(errorText(e, 'Could not load payments.')))
  useEffect(() => { loadRows() }, [sponsorId]) // eslint-disable-line react-hooks/exhaustive-deps

  const link = async (purpose: 'deposit' | 'balance') => {
    try {
      const r = await adminAPI.paymentLink(sponsorId, purpose, linkAmount ? nairaToKobo(linkAmount) : undefined)
      setLastLink(r.authorization_url)
      const copied = await copyText(r.authorization_url)
      ok(`Paystack link for ${formatNaira(r.amount_kobo)} ${copied ? 'copied' : 'created'}. Send it to ${data.organization.contact_email}.`)
      loadRows()
    } catch (e) {
      fail(errorText(e, 'Could not create a payment link.'))
    }
  }

  const record = async () => {
    const kobo = nairaToKobo(transfer.amount)
    if (!(await confirm({
      title: `Record ${formatNaira(kobo)} from ${data.organization.name}?`,
      body: <>Only record money that has <b>arrived in the bank</b>. Note: “{transfer.note}”.</>,
      confirmLabel: 'Record transfer',
    }))) return
    const done = await run(() => adminAPI.manualPayment(sponsorId, kobo, transfer.note, transfer.date ? `${transfer.date}T12:00:00` : undefined), 'Transfer recorded.')
    if (done) { setTransfer({ amount: '', note: '', date: '' }); loadRows() }
  }

  const voidIt = async (p: AdminPayment) => {
    const reason = await confirm({
      title: `Void ${formatNaira(p.amount_kobo)}?`, body: 'Use this only for a transfer recorded by mistake.',
      confirmLabel: 'Void', danger: true, reason: true,
    })
    if (!reason) return
    if (await run(() => adminAPI.voidPayment(p.reference, reason), 'Payment voided.')) loadRows()
  }

  return (
    <Grid container spacing={3}>
      <Grid item xs={12} md={6}>
        <Typography fontWeight={700} sx={{ mb: 1 }}>Ask for payment (Paystack)</Typography>
        {!data.payments_enabled && <Alert severity="warning" sx={{ mb: 1 }}>Paystack isn't configured on this server — record bank transfers instead.</Alert>}
        <TextField size="small" label="Custom amount (₦, optional)" value={linkAmount} onChange={(e) => setLinkAmount(e.target.value)}
          helperText="Blank = the outstanding deposit or amount due" sx={{ mb: 1 }} fullWidth />
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" disabled={!data.payments_enabled || (!a.deposit_outstanding_kobo && !linkAmount)} onClick={() => link('deposit')}>
            Deposit link{a.deposit_outstanding_kobo ? ` (${formatNaira(a.deposit_outstanding_kobo)})` : ''}
          </Button>
          <Button variant="outlined" disabled={!data.payments_enabled || (!a.amount_due_kobo && !linkAmount)} onClick={() => link('balance')}>
            Balance link{a.amount_due_kobo ? ` (${formatNaira(a.amount_due_kobo)})` : ''}
          </Button>
        </Stack>
        {lastLink && <Typography variant="caption" sx={{ display: 'block', mt: 1, wordBreak: 'break-all' }}>{lastLink}<Copyable text={lastLink} /></Typography>}
      </Grid>
      <Grid item xs={12} md={6}>
        <Typography fontWeight={700} sx={{ mb: 1 }}>Record a bank transfer</Typography>
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1.5}>
            <TextField size="small" label="Amount (₦)" value={transfer.amount} onChange={(e) => setTransfer({ ...transfer, amount: e.target.value })} fullWidth />
            <TextField size="small" type="date" label="Date received" value={transfer.date} onChange={(e) => setTransfer({ ...transfer, date: e.target.value })} InputLabelProps={{ shrink: true }} fullWidth />
          </Stack>
          <TextField size="small" label="Note (bank, reference, payer)" value={transfer.note} onChange={(e) => setTransfer({ ...transfer, note: e.target.value })} />
          <Box><Button variant="contained" onClick={record} disabled={!transfer.amount || !(nairaToKobo(transfer.amount) > 0) || transfer.note.trim().length < 3}>Record</Button></Box>
        </Stack>
      </Grid>
      <Grid item xs={12}>
        <Divider sx={{ mb: 2 }} />
        <Typography fontWeight={700} sx={{ mb: 1 }}>History</Typography>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead><TableRow><TableCell>Date</TableCell><TableCell>Type</TableCell><TableCell align="right">Amount</TableCell><TableCell>Status</TableCell><TableCell>Reference / note</TableCell><TableCell /></TableRow></TableHead>
            <TableBody>
              {rows.length === 0 && <TableRow><TableCell colSpan={6} align="center" sx={{ py: 3, color: 'text.secondary' }}>No payments yet.</TableCell></TableRow>}
              {rows.map((p) => (
                <TableRow key={p.reference}>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>{fmtDate(p.paid_at || p.created_at, true)}</TableCell>
                  <TableCell>{p.purpose.replace('sponsor_', '').replace('manual', 'bank transfer')}</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>{formatNaira(p.amount_kobo)}</TableCell>
                  <TableCell><StatusChip status={p.status} /></TableCell>
                  <TableCell sx={{ maxWidth: 300 }}><Typography variant="caption" display="block">{p.reference}</Typography>
                    {p.note && <Typography variant="caption" color="text.secondary" sx={{ wordBreak: 'break-word' }}>{p.note}</Typography>}</TableCell>
                  <TableCell>{p.purpose === 'sponsor_manual' && p.status === 'success' && <Button size="small" color="error" onClick={() => voidIt(p)}>Void</Button>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      </Grid>
    </Grid>
  )
}

// ---------------------------------------------------------------------------

const StatementTab: React.FC<{ sponsorId: number }> = ({ sponsorId }) => {
  const options = months()
  const [sel, setSel] = useState(`${options[0].y}-${options[0].m}`)
  const [s, setS] = useState<SponsorStatement | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    const [y, m] = sel.split('-').map(Number)
    setS(null)
    adminAPI.sponsorStatement(sponsorId, y, m).then(setS).catch((e) => setErr(errorText(e, 'Could not load the statement.')))
  }, [sponsorId, sel])
  return (
    <>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
        <TextField select size="small" label="Month" value={sel} onChange={(e) => setSel(e.target.value)} sx={{ minWidth: 200 }}>
          {options.map((o) => <MenuItem key={`${o.y}-${o.m}`} value={`${o.y}-${o.m}`}>{o.label}</MenuItem>)}
        </TextField>
        <Button variant="outlined" size="small" onClick={() => window.print()}>Print</Button>
      </Stack>
      {err && <Alert severity="error">{err}</Alert>}
      {!s && !err && <LinearProgress />}
      {s && (
        <>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={6} md={2.4}><StatCard label="Opening balance" value={formatNaira(s.opening_balance_kobo)} /></Grid>
            <Grid item xs={6} md={2.4}><StatCard label="Certificates" value={s.certificates_issued} hint={`@ ${formatNaira(s.price_per_certificate_kobo)}`} /></Grid>
            <Grid item xs={6} md={2.4}><StatCard label="Charges" value={formatNaira(s.charges_kobo)} /></Grid>
            <Grid item xs={6} md={2.4}><StatCard label="Payments" value={formatNaira(s.payments_kobo)} tone="good" /></Grid>
            <Grid item xs={12} md={2.4}><StatCard label="Closing balance" value={formatNaira(s.closing_balance_kobo)} tone={s.amount_due_kobo ? 'bad' : 'default'} /></Grid>
          </Grid>
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <Typography fontWeight={700} sx={{ mb: 1 }}>Charges</Typography>
              <Table size="small"><TableBody>
                {s.charges.length === 0 && <TableRow><TableCell sx={{ color: 'text.secondary' }}>None this month.</TableCell></TableRow>}
                {s.charges.map((c) => <TableRow key={c.certificate_id}><TableCell>{fmtDate(c.issued_at)}</TableCell><TableCell>{c.certificate_id}</TableCell><TableCell align="right">{formatNaira(c.amount_kobo)}</TableCell></TableRow>)}
              </TableBody></Table>
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography fontWeight={700} sx={{ mb: 1 }}>Payments</Typography>
              <Table size="small"><TableBody>
                {s.payments.length === 0 && <TableRow><TableCell sx={{ color: 'text.secondary' }}>None this month.</TableCell></TableRow>}
                {s.payments.map((p) => <TableRow key={p.reference}><TableCell>{fmtDate(p.paid_at)}</TableCell><TableCell>{p.purpose.replace('sponsor_', '')}</TableCell><TableCell align="right">{formatNaira(p.amount_kobo)}</TableCell></TableRow>)}
              </TableBody></Table>
            </Grid>
          </Grid>
        </>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------

const SettingsTab: React.FC<{ data: Detail; run: Run }> = ({ data, run }) => {
  const o = data.organization
  const initial = {
    name: o.name, package: o.package, contact_email: o.contact_email, contact_name: o.contact_name || '',
    contact_phone: o.contact_phone || '', price: String(o.price_per_certificate_kobo / 100), deposit: String(o.deposit_kobo / 100),
    cap: o.learner_cap ? String(o.learner_cap) : '', notes: o.notes || '',
  }
  const [f, setF] = useState(initial)
  const [portal, setPortal] = useState({ email: o.portal_email || '', password: '' })
  const set = (k: keyof typeof initial) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value })

  const saveProfile = () => {
    const body: Record<string, unknown> = {}
    if (f.name !== initial.name) body.name = f.name
    if (f.package !== initial.package) body.package = f.package
    if (f.contact_email !== initial.contact_email) body.contact_email = f.contact_email
    if (f.contact_name !== initial.contact_name) body.contact_name = f.contact_name || null
    if (f.contact_phone !== initial.contact_phone) body.contact_phone = f.contact_phone || null
    if (f.price !== initial.price) body.price_per_certificate_kobo = nairaToKobo(f.price)
    if (f.deposit !== initial.deposit) body.deposit_kobo = nairaToKobo(f.deposit)
    if (f.cap !== initial.cap) { if (f.cap) body.learner_cap = Number(f.cap); else body.clear_learner_cap = true }
    if (f.notes !== initial.notes) body.notes = f.notes || null
    if (!Object.keys(body).length) return
    run(() => adminAPI.updateSponsor(o.id, body), 'Sponsor saved.')
  }

  const savePortal = async () => {
    const body: Record<string, unknown> = {}
    if (portal.email && portal.email !== o.portal_email) body.portal_email = portal.email
    if (portal.password) body.portal_password = portal.password
    if (!Object.keys(body).length) return
    if (await run(() => adminAPI.updateSponsor(o.id, body), portal.password ? 'Portal login saved. Send the sponsor their new password securely.' : 'Portal email saved.')) {
      setPortal({ ...portal, password: '' })
    }
  }

  return (
    <Grid container spacing={3}>
      <Grid item xs={12} md={7}>
        <Typography fontWeight={700} sx={{ mb: 1.5 }}>Profile and pricing</Typography>
        <Stack spacing={2}>
          <TextField label="Organisation name" value={f.name} onChange={set('name')} />
          <TextField select label="Package" value={f.package} onChange={set('package')}>
            {PACKAGES.map((p) => <MenuItem key={p.value} value={p.value}>{p.label}</MenuItem>)}
          </TextField>
          <Stack direction="row" spacing={2}>
            <TextField label="Price per certificate (₦)" value={f.price} onChange={set('price')} fullWidth
              helperText="Applies to certificates issued from now on; past ones keep their price." />
            <TextField label="Deposit (₦)" value={f.deposit} onChange={set('deposit')} fullWidth />
          </Stack>
          <TextField label="Learner cap (blank = no cap)" value={f.cap} onChange={(e) => setF({ ...f, cap: e.target.value.replace(/\D/g, '') })} />
          <Stack direction="row" spacing={2}>
            <TextField label="Billing email" value={f.contact_email} onChange={set('contact_email')} fullWidth />
            <TextField label="Contact name" value={f.contact_name} onChange={set('contact_name')} fullWidth />
          </Stack>
          <TextField label="Contact phone" value={f.contact_phone} onChange={set('contact_phone')} />
          <TextField label="Internal notes" multiline minRows={3} value={f.notes} onChange={set('notes')} />
          <Stack direction="row" spacing={1}>
            <Button variant="contained" onClick={saveProfile}>Save changes</Button>
            <Button onClick={() => setF(initial)}>Reset</Button>
          </Stack>
        </Stack>
      </Grid>
      <Grid item xs={12} md={5}>
        <Paper elevation={0} sx={{ ...card, mb: 2 }}>
          <Typography fontWeight={700} sx={{ mb: 1 }}>Sponsor portal login</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            {o.portal_email ? <>The sponsor signs in at <b>/sponsor</b> with {o.portal_email}.</> : 'No portal login yet.'}
            {' '}Set a new password if they forget theirs.
          </Typography>
          <Stack spacing={1.5}>
            <TextField size="small" label="Portal email" value={portal.email} onChange={(e) => setPortal({ ...portal, email: e.target.value })} />
            <TextField size="small" type="password" label={o.has_portal_password ? 'New password (10+ chars)' : 'Password (10+ chars)'} value={portal.password}
              onChange={(e) => setPortal({ ...portal, password: e.target.value })} />
            <Box><Button variant="outlined" onClick={savePortal}
              disabled={(!!portal.password && portal.password.length < 10) || (!o.portal_email && (!portal.email || !portal.password))}>Save login</Button></Box>
          </Stack>
        </Paper>
        <Paper elevation={0} sx={card}>
          <Typography fontWeight={700} sx={{ mb: 1 }}>Logo on certificates</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            {o.has_logo ? 'A logo is on file.' : 'No logo — certificates show the sponsor name only.'} PNG or JPEG, up to 1 MB. Applies to new certificates.
          </Typography>
          <Button variant="outlined" component="label">
            {o.has_logo ? 'Replace logo' : 'Upload logo'}
            <input hidden type="file" accept="image/png,image/jpeg"
              onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ''; if (file) run(() => adminAPI.uploadLogo(o.id, file), 'Logo saved.') }} />
          </Button>
        </Paper>
        <AdvertModeration data={data} run={run} />
      </Grid>
    </Grid>
  )
}

const AdvertModeration: React.FC<{ data: Detail; run: Run }> = ({ data, run }) => {
  const o = data.organization
  const b = data.branding
  const page = data.codes.find((c) => c.is_active)
  const status = b.ad_suspended ? 'Paused by MNAIR' : b.ad_live ? 'Live to learners' : b.ad_enabled ? 'On, but no headline' : 'Off (sponsor)'
  return (
    <Paper elevation={0} sx={{ ...card, mt: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
        <Typography fontWeight={700}>Branded page and advert</Typography>
        <Chip size="small" label={status} color={b.ad_live ? 'success' : b.ad_suspended ? 'warning' : 'default'} />
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        The sponsor edits this in their portal. Pausing hides the advert everywhere, and the sponsor cannot turn it back on.
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
        <Box sx={{ width: 20, height: 20, borderRadius: '50%', bgcolor: b.brand_color || '#008751', border: '1px solid', borderColor: 'grey.300' }} />
        <Typography variant="body2">{b.brand_color || 'Default colour'}</Typography>
        {page && (
          <Link href={`/s/${encodeURIComponent(page.code)}`} target="_blank" rel="noopener noreferrer" variant="body2" sx={{ ml: 'auto' }}>
            Open their page
          </Link>
        )}
      </Stack>
      {b.ad_headline && (
        <Box sx={{ mb: 1.5 }}>
          <SponsorAdvertCard
            variant="compact"
            sponsorName={o.name}
            advert={{ headline: b.ad_headline, body: b.ad_body, cta_label: b.ad_cta_label, cta_url: b.ad_cta_url, image_url: b.ad_image_url }}
          />
        </Box>
      )}
      <Button
        variant="outlined"
        color={b.ad_suspended ? 'success' : 'warning'}
        onClick={() => run(() => adminAPI.updateSponsor(o.id, { ad_suspended: !b.ad_suspended }), b.ad_suspended ? 'Advert allowed again.' : 'Advert paused.')}
      >
        {b.ad_suspended ? 'Allow advert' : 'Pause advert'}
      </Button>
    </Paper>
  )
}

export default SponsorDetail
