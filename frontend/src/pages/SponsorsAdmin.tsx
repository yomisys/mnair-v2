import React, { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
import apiClient, { formatNaira } from '../services/api'

/**
 * Admin: sponsors. Create a sponsor (package prices fill in), hand out
 * codes, upload a logo, send a Paystack link, or record a bank transfer.
 */

interface SponsorRow {
  id: number; name: string; package: string; is_active: boolean
  price_per_certificate_kobo: number; deposit_kobo: number; learner_cap: number | null
  enrolled: number; certificates_billed: number; charged_kobo: number; paid_kobo: number
  amount_due_kobo: number; credit_remaining_kobo: number; deposit_outstanding_kobo: number
  contact_email: string; portal_email: string | null
}
interface CodeRow { id: number; code: string; label: string | null; is_active: boolean; join_url: string; telegram_url: string | null }

const PACKAGES = [
  { value: 'community', label: 'Community — ₦2,500 / cert, ₦125,000 deposit' },
  { value: 'organisation', label: 'Organisation — ₦2,000 / cert, ₦1,000,000 deposit' },
  { value: 'enterprise', label: 'Enterprise — ₦1,500 / cert, ₦7,500,000 deposit' },
  { value: 'national', label: 'National — set prices' },
]

const errorText = (e: unknown, fallback: string): string => {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg).replace(/^Value error, /, '')
  return fallback
}

const nairaToKobo = (v: string) => Math.round(parseFloat(v.replace(/[^\d.]/g, '')) * 100)

const blankForm = {
  name: '', package: 'community', contact_email: '', contact_name: '', learner_cap: '',
  portal_email: '', portal_password: '', first_code: '', price_naira: '', deposit_naira: '',
}

const SponsorsAdmin: React.FC = () => {
  const [rows, setRows] = useState<SponsorRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState({ ...blankForm })
  const [selected, setSelected] = useState<SponsorRow | null>(null)
  const [codes, setCodes] = useState<CodeRow[]>([])
  const [transfer, setTransfer] = useState({ amount: '', note: '' })

  const load = async () => {
    try {
      setRows((await apiClient.get('/api/v1/admin/sponsors')).data)
    } catch (e) {
      setError(errorText(e, 'Could not load sponsors.'))
    }
  }

  useEffect(() => { load() }, [])

  const openSponsor = async (row: SponsorRow) => {
    setSelected(row)
    setTransfer({ amount: '', note: '' })
    try {
      setCodes((await apiClient.get(`/api/v1/admin/sponsors/${row.id}/codes`)).data)
    } catch (e) {
      setError(errorText(e, 'Could not load codes.'))
    }
  }

  const create = async () => {
    setError(null)
    const body: Record<string, unknown> = {
      name: form.name, package: form.package, contact_email: form.contact_email,
      contact_name: form.contact_name || undefined,
      learner_cap: form.learner_cap ? Number(form.learner_cap) : undefined,
      first_code: form.first_code || undefined,
    }
    if (form.portal_email) { body.portal_email = form.portal_email; body.portal_password = form.portal_password }
    if (form.price_naira) body.price_per_certificate_kobo = nairaToKobo(form.price_naira)
    if (form.deposit_naira) body.deposit_kobo = nairaToKobo(form.deposit_naira)
    try {
      const r = (await apiClient.post('/api/v1/admin/sponsors', body)).data
      setCreateOpen(false)
      setForm({ ...blankForm })
      setNotice(`Created ${r.name}. Code ${r.code.code} — join link ${r.code.join_url}`)
      load()
    } catch (e) {
      setError(errorText(e, 'Could not create the sponsor.'))
    }
  }

  const addCode = async () => {
    if (!selected) return
    const label = window.prompt('Label for the new code (e.g. "Youth church, Ikeja"):') || undefined
    try {
      await apiClient.post(`/api/v1/admin/sponsors/${selected.id}/codes`, { label })
      openSponsor(selected)
    } catch (e) {
      setError(errorText(e, 'Could not add a code.'))
    }
  }

  const toggleCode = async (c: CodeRow) => {
    try {
      await apiClient.patch(`/api/v1/admin/sponsors/codes/${c.id}`, { is_active: !c.is_active })
      if (selected) openSponsor(selected)
    } catch (e) {
      setError(errorText(e, 'Could not update the code.'))
    }
  }

  const paymentLink = async (purpose: 'deposit' | 'balance') => {
    if (!selected) return
    try {
      const r = (await apiClient.post(`/api/v1/admin/sponsors/${selected.id}/payment-link`, { purpose })).data
      await navigator.clipboard?.writeText(r.authorization_url)
      setNotice(`Paystack link for ${formatNaira(r.amount_kobo)} copied: ${r.authorization_url}`)
    } catch (e) {
      setError(errorText(e, 'Could not create a payment link.'))
    }
  }

  const recordTransfer = async () => {
    if (!selected) return
    try {
      await apiClient.post(`/api/v1/admin/sponsors/${selected.id}/manual-payment`, {
        amount_kobo: nairaToKobo(transfer.amount), note: transfer.note,
      })
      setNotice(`Recorded ₦${transfer.amount} from ${selected.name}.`)
      setSelected(null)
      load()
    } catch (e) {
      setError(errorText(e, 'Could not record the transfer.'))
    }
  }

  const uploadLogo = async (file: File) => {
    if (!selected) return
    const data = new FormData()
    data.append('file', file)
    try {
      await apiClient.post(`/api/v1/admin/sponsors/${selected.id}/logo`, data, { headers: { 'Content-Type': 'multipart/form-data' } })
      setNotice(`Logo saved for ${selected.name}. New certificates will carry it.`)
    } catch (e) {
      setError(errorText(e, 'Could not upload the logo.'))
    }
  }

  const set = (k: keyof typeof blankForm) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value })

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h5" fontWeight={800}>Sponsors</Typography>
          <Typography variant="body2" color="text.secondary">Sponsors pay per certified learner. Billing is live from these numbers.</Typography>
        </Box>
        <Button variant="contained" onClick={() => setCreateOpen(true)}>New sponsor</Button>
      </Stack>

      {error && <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>{error}</Alert>}
      {notice && <Alert severity="success" onClose={() => setNotice(null)} sx={{ mb: 2, wordBreak: 'break-all' }}>{notice}</Alert>}

      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'grey.200', overflowX: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Sponsor</TableCell><TableCell>Package</TableCell>
              <TableCell align="right">Enrolled</TableCell><TableCell align="right">Certified</TableCell>
              <TableCell align="right">Charged</TableCell><TableCell align="right">Paid</TableCell>
              <TableCell align="right">Due</TableCell><TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={8} align="center" sx={{ py: 4, color: 'text.secondary' }}>No sponsors yet.</TableCell></TableRow>
            )}
            {rows.map((r) => (
              <TableRow key={r.id} hover>
                <TableCell>
                  <strong>{r.name}</strong>{!r.is_active && <Chip size="small" label="inactive" sx={{ ml: 1 }} />}
                  <Typography variant="caption" display="block" color="text.secondary">{r.contact_email}</Typography>
                </TableCell>
                <TableCell>{r.package} · {formatNaira(r.price_per_certificate_kobo)}</TableCell>
                <TableCell align="right">{r.enrolled}{r.learner_cap ? ` / ${r.learner_cap}` : ''}</TableCell>
                <TableCell align="right">{r.certificates_billed}</TableCell>
                <TableCell align="right">{formatNaira(r.charged_kobo)}</TableCell>
                <TableCell align="right">{formatNaira(r.paid_kobo)}</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700, color: r.amount_due_kobo ? 'error.main' : 'inherit' }}>
                  {formatNaira(r.amount_due_kobo)}
                </TableCell>
                <TableCell><Button size="small" onClick={() => openSponsor(r)}>Manage</Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>

      {/* create */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New sponsor</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Organisation name" value={form.name} onChange={set('name')} required />
            <TextField select label="Package" value={form.package} onChange={set('package')}>
              {PACKAGES.map((p) => <MenuItem key={p.value} value={p.value}>{p.label}</MenuItem>)}
            </TextField>
            {form.package === 'national' && (
              <Stack direction="row" spacing={2}>
                <TextField label="Price per certificate (₦)" value={form.price_naira} onChange={set('price_naira')} fullWidth />
                <TextField label="Deposit (₦)" value={form.deposit_naira} onChange={set('deposit_naira')} fullWidth />
              </Stack>
            )}
            <Stack direction="row" spacing={2}>
              <TextField label="Billing email" type="email" value={form.contact_email} onChange={set('contact_email')} required fullWidth />
              <TextField label="Contact name" value={form.contact_name} onChange={set('contact_name')} fullWidth />
            </Stack>
            <Stack direction="row" spacing={2}>
              <TextField label="Learner cap (optional)" value={form.learner_cap} onChange={set('learner_cap')} fullWidth />
              <TextField label="Code (optional)" placeholder="e.g. GRACE-2026" value={form.first_code} onChange={set('first_code')} fullWidth />
            </Stack>
            <Typography variant="body2" color="text.secondary">Dashboard login for the sponsor (optional, can be added later):</Typography>
            <Stack direction="row" spacing={2}>
              <TextField label="Portal email" type="email" value={form.portal_email} onChange={set('portal_email')} fullWidth />
              <TextField label="Portal password (10+ chars)" type="password" value={form.portal_password} onChange={set('portal_password')} fullWidth />
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={create} disabled={!form.name || !form.contact_email}>Create</Button>
        </DialogActions>
      </Dialog>

      {/* manage */}
      <Dialog open={!!selected} onClose={() => setSelected(null)} fullWidth maxWidth="md">
        <DialogTitle>{selected?.name}</DialogTitle>
        <DialogContent>
          <Typography fontWeight={700} sx={{ mb: 1 }}>Codes</Typography>
          <Table size="small" sx={{ mb: 2 }}>
            <TableBody>
              {codes.map((c) => (
                <TableRow key={c.id}>
                  <TableCell><strong>{c.code}</strong></TableCell>
                  <TableCell>{c.label || '–'}</TableCell>
                  <TableCell sx={{ wordBreak: 'break-all' }}>{c.join_url}</TableCell>
                  <TableCell>
                    <Button size="small" color={c.is_active ? 'error' : 'primary'} onClick={() => toggleCode(c)}>
                      {c.is_active ? 'Deactivate' : 'Activate'}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Stack direction="row" spacing={1} sx={{ mb: 3 }} flexWrap="wrap" gap={1}>
            <Button variant="outlined" onClick={addCode}>Add code</Button>
            <Button variant="outlined" component="label">
              Upload logo (PNG/JPEG, 1 MB)
              <input hidden type="file" accept="image/png,image/jpeg" onChange={(e) => e.target.files?.[0] && uploadLogo(e.target.files[0])} />
            </Button>
            <Button variant="outlined" disabled={!selected?.deposit_outstanding_kobo} onClick={() => paymentLink('deposit')}>Copy deposit pay link</Button>
            <Button variant="outlined" disabled={!selected?.amount_due_kobo} onClick={() => paymentLink('balance')}>Copy balance pay link</Button>
          </Stack>

          <Typography fontWeight={700} sx={{ mb: 1 }}>Record a bank transfer</Typography>
          <Stack direction="row" spacing={2}>
            <TextField label="Amount (₦)" value={transfer.amount} onChange={(e) => setTransfer({ ...transfer, amount: e.target.value })} />
            <TextField label="Note (bank, ref, date)" value={transfer.note} onChange={(e) => setTransfer({ ...transfer, note: e.target.value })} fullWidth />
            <Button variant="contained" onClick={recordTransfer} disabled={!transfer.amount || transfer.note.length < 3}>Record</Button>
          </Stack>
        </DialogContent>
        <DialogActions><Button onClick={() => setSelected(null)}>Close</Button></DialogActions>
      </Dialog>
    </Box>
  )
}

export default SponsorsAdmin
