import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
  TableSortLabel,
  TextField,
  Typography,
} from '@mui/material'
import { adminAPI, formatNaira } from '../services/api'
import { exportCSV } from '../components/ExportButton'
import {
  errorText, FilterSelect, nairaToKobo, PageHeader, SearchBox, StatCard, StatusChip, useNotice,
} from '../components/AdminKit'

/**
 * Admin: sponsors. Totals across all sponsors, search and filter, and a
 * "New sponsor" form (package prices fill in). Each row opens the sponsor
 * page (/dashboard/sponsors/:id) where everything else is managed.
 */

export interface SponsorRow {
  id: number; name: string; package: string; is_active: boolean
  price_per_certificate_kobo: number; deposit_kobo: number; learner_cap: number | null
  enrolled: number; certificates_billed: number; charged_kobo: number; paid_kobo: number
  amount_due_kobo: number; credit_remaining_kobo: number; deposit_outstanding_kobo: number
  contact_email: string; portal_email: string | null
}

export const PACKAGES = [
  { value: 'community', label: 'Community — ₦2,500 / cert, ₦125,000 deposit' },
  { value: 'organisation', label: 'Organisation — ₦2,000 / cert, ₦1,000,000 deposit' },
  { value: 'enterprise', label: 'Enterprise — ₦1,500 / cert, ₦7,500,000 deposit' },
  { value: 'national', label: 'National — set prices' },
]

const blankForm = {
  name: '', package: 'community', contact_email: '', contact_name: '', contact_phone: '', learner_cap: '',
  portal_email: '', portal_password: '', first_code: '', price_naira: '', deposit_naira: '', notes: '',
}

type SortKey = 'name' | 'enrolled' | 'certificates_billed' | 'charged_kobo' | 'paid_kobo' | 'amount_due_kobo'

const SponsorsAdmin: React.FC = () => {
  const navigate = useNavigate()
  const [rows, setRows] = useState<SponsorRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState({ ...blankForm })
  const [formError, setFormError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [q, setQ] = useState('')
  const [pkg, setPkg] = useState('')
  const [state, setState] = useState('')
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({ key: 'amount_due_kobo', dir: 'desc' })
  const { ok, notice } = useNotice()

  const load = async () => {
    setLoading(true)
    try {
      setRows(await adminAPI.sponsors())
      setError(null)
    } catch (e) {
      setError(errorText(e, 'Could not load sponsors.'))
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const out = rows.filter((r) =>
      (!needle || r.name.toLowerCase().includes(needle) || r.contact_email.toLowerCase().includes(needle)) &&
      (!pkg || r.package === pkg) &&
      (!state || (state === 'active' ? r.is_active : state === 'inactive' ? !r.is_active : r.amount_due_kobo > 0)))
    const k = sort.key
    out.sort((a, b) => {
      const v = k === 'name' ? a.name.localeCompare(b.name) : (a[k] as number) - (b[k] as number)
      return sort.dir === 'asc' ? v : -v
    })
    return out
  }, [rows, q, pkg, state, sort])

  const sum = (k: keyof SponsorRow) => rows.reduce((s, r) => s + (r[k] as number), 0)

  const create = async () => {
    setFormError(null)
    const body: Record<string, unknown> = {
      name: form.name, package: form.package, contact_email: form.contact_email,
      contact_name: form.contact_name || undefined, contact_phone: form.contact_phone || undefined,
      learner_cap: form.learner_cap ? Number(form.learner_cap) : undefined,
      first_code: form.first_code || undefined, notes: form.notes || undefined,
    }
    if (form.portal_email) { body.portal_email = form.portal_email; body.portal_password = form.portal_password }
    if (form.price_naira) body.price_per_certificate_kobo = nairaToKobo(form.price_naira)
    if (form.deposit_naira) body.deposit_kobo = nairaToKobo(form.deposit_naira)
    setSaving(true)
    try {
      const r = await adminAPI.createSponsor(body)
      setCreateOpen(false)
      setForm({ ...blankForm })
      ok(`Created ${r.name}. Code ${r.code.code}.`)
      navigate(`/dashboard/sponsors/${r.id}`)
    } catch (e) {
      setFormError(errorText(e, 'Could not create the sponsor.'))
    } finally {
      setSaving(false)
    }
  }

  const set = (k: keyof typeof blankForm) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value })
  const head = (key: SortKey, label: string, right = true) => (
    <TableCell align={right ? 'right' : 'left'} sortDirection={sort.key === key ? sort.dir : false}>
      <TableSortLabel active={sort.key === key} direction={sort.key === key ? sort.dir : 'desc'}
        onClick={() => setSort({ key, dir: sort.key === key && sort.dir === 'desc' ? 'asc' : 'desc' })}>{label}</TableSortLabel>
    </TableCell>
  )

  return (
    <Box sx={{ p: 3 }}>
      <PageHeader
        title="Sponsors"
        subtitle="Sponsors pay per certified learner. Billing is live from these numbers."
        actions={<>
          <Button variant="outlined" disabled={!rows.length} onClick={() => exportCSV('mnair-sponsors.csv', shown.map((r) => ({
            name: r.name, package: r.package, active: r.is_active, contact_email: r.contact_email,
            price_naira: r.price_per_certificate_kobo / 100, enrolled: r.enrolled, certified: r.certificates_billed,
            charged_naira: r.charged_kobo / 100, paid_naira: r.paid_kobo / 100, due_naira: r.amount_due_kobo / 100,
            deposit_outstanding_naira: r.deposit_outstanding_kobo / 100,
          })))}>Export CSV</Button>
          <Button variant="contained" onClick={() => { setFormError(null); setCreateOpen(true) }}>New sponsor</Button>
        </>}
      />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><StatCard label="Active sponsors" value={rows.filter((r) => r.is_active).length} hint={`${rows.length} in total`} /></Grid>
        <Grid item xs={6} md={3}><StatCard label="Sponsored learners" value={sum('enrolled').toLocaleString()} hint={`${sum('certificates_billed').toLocaleString()} certified`} /></Grid>
        <Grid item xs={6} md={3}><StatCard label="Collected" value={formatNaira(sum('paid_kobo'))} hint={`of ${formatNaira(sum('charged_kobo'))} billed`} tone="good" /></Grid>
        <Grid item xs={6} md={3}><StatCard label="Outstanding" value={formatNaira(sum('amount_due_kobo'))}
          hint={`${rows.filter((r) => r.amount_due_kobo > 0).length} sponsors owe · deposits ${formatNaira(sum('deposit_outstanding_kobo'))}`}
          tone={sum('amount_due_kobo') ? 'bad' : 'default'} /></Grid>
      </Grid>

      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        <SearchBox value={q} onChange={setQ} placeholder="Sponsor name or billing email" />
        <FilterSelect label="Package" value={pkg} onChange={setPkg} options={PACKAGES.map((p) => ({ value: p.value, label: p.value }))} />
        <FilterSelect label="Show" value={state} onChange={setState} options={[
          { value: 'active', label: 'Active' }, { value: 'inactive', label: 'Inactive' }, { value: 'owing', label: 'Owing money' },
        ]} />
      </Stack>

      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'grey.200', overflowX: 'auto' }}>
        {loading && <LinearProgress />}
        <Table size="small">
          <TableHead>
            <TableRow>
              {head('name', 'Sponsor', false)}<TableCell>Package</TableCell>
              {head('enrolled', 'Enrolled')}{head('certificates_billed', 'Certified')}
              {head('charged_kobo', 'Billed')}{head('paid_kobo', 'Paid')}{head('amount_due_kobo', 'Due')}
            </TableRow>
          </TableHead>
          <TableBody>
            {!loading && shown.length === 0 && (
              <TableRow><TableCell colSpan={7} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                {rows.length ? 'No sponsors match.' : 'No sponsors yet. Click “New sponsor” to add the first.'}
              </TableCell></TableRow>
            )}
            {shown.map((r) => (
              <TableRow key={r.id} hover sx={{ cursor: 'pointer' }} onClick={() => navigate(`/dashboard/sponsors/${r.id}`)}>
                <TableCell>
                  <strong>{r.name}</strong>{!r.is_active && <Box component="span" sx={{ ml: 1 }}><StatusChip status="inactive" /></Box>}
                  <Typography variant="caption" display="block" color="text.secondary">{r.contact_email}</Typography>
                </TableCell>
                <TableCell>
                  <Chip size="small" label={r.package} variant="outlined" /> {formatNaira(r.price_per_certificate_kobo)}
                  {r.deposit_outstanding_kobo > 0 && <Typography variant="caption" display="block" color="warning.dark">deposit {formatNaira(r.deposit_outstanding_kobo)} unpaid</Typography>}
                </TableCell>
                <TableCell align="right">{r.enrolled.toLocaleString()}{r.learner_cap ? ` / ${r.learner_cap.toLocaleString()}` : ''}</TableCell>
                <TableCell align="right">{r.certificates_billed.toLocaleString()}</TableCell>
                <TableCell align="right">{formatNaira(r.charged_kobo)}</TableCell>
                <TableCell align="right">{formatNaira(r.paid_kobo)}</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700, color: r.amount_due_kobo ? 'error.main' : r.credit_remaining_kobo ? 'success.main' : 'inherit' }}>
                  {r.amount_due_kobo ? formatNaira(r.amount_due_kobo) : r.credit_remaining_kobo ? `${formatNaira(r.credit_remaining_kobo)} credit` : '₦0'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New sponsor</DialogTitle>
        <DialogContent>
          {formError && <Alert severity="error" sx={{ mt: 1 }}>{formError}</Alert>}
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Organisation name" value={form.name} onChange={set('name')} required />
            <TextField select label="Package" value={form.package} onChange={set('package')}>
              {PACKAGES.map((p) => <MenuItem key={p.value} value={p.value}>{p.label}</MenuItem>)}
            </TextField>
            <Stack direction="row" spacing={2}>
              <TextField label={`Price per certificate (₦)${form.package === 'national' ? '' : ' — optional override'}`} value={form.price_naira}
                onChange={set('price_naira')} required={form.package === 'national'} fullWidth />
              <TextField label={`Deposit (₦)${form.package === 'national' ? '' : ' — optional'}`} value={form.deposit_naira}
                onChange={set('deposit_naira')} required={form.package === 'national'} fullWidth />
            </Stack>
            <Stack direction="row" spacing={2}>
              <TextField label="Billing email" type="email" value={form.contact_email} onChange={set('contact_email')} required fullWidth />
              <TextField label="Contact name" value={form.contact_name} onChange={set('contact_name')} fullWidth />
            </Stack>
            <Stack direction="row" spacing={2}>
              <TextField label="Contact phone" value={form.contact_phone} onChange={set('contact_phone')} fullWidth />
              <TextField label="Learner cap (optional)" value={form.learner_cap} onChange={set('learner_cap')} fullWidth />
            </Stack>
            <TextField label="First code (optional)" placeholder="e.g. GRACE-2026 — generated if blank" value={form.first_code} onChange={set('first_code')} />
            <Typography variant="body2" color="text.secondary">Dashboard login for the sponsor (optional, can be added later):</Typography>
            <Stack direction="row" spacing={2}>
              <TextField label="Portal email" type="email" value={form.portal_email} onChange={set('portal_email')} fullWidth />
              <TextField label="Portal password (10+ chars)" type="password" value={form.portal_password} onChange={set('portal_password')} fullWidth />
            </Stack>
            <TextField label="Internal notes" multiline minRows={2} value={form.notes} onChange={set('notes')} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={create}
            disabled={saving || !form.name || !form.contact_email || (form.package === 'national' && (!form.price_naira || !form.deposit_naira))}>
            Create
          </Button>
        </DialogActions>
      </Dialog>
      {notice}
    </Box>
  )
}

export default SponsorsAdmin
