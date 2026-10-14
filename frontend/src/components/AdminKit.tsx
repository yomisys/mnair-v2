import React, { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControlLabel,
  IconButton,
  InputAdornment,
  MenuItem,
  Paper,
  Snackbar,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import {
  ContentCopy as CopyIcon,
  Download as DownloadIcon,
  Link as LinkIcon,
  Search as SearchIcon,
} from '@mui/icons-material'
import { saveBlob, ShareLink } from '../services/api'

/** Shared building blocks for the admin back office pages. */

export const errorText = (e: unknown, fallback: string): string => {
  const detail = (e as { response?: { data?: unknown } })?.response?.data as { detail?: unknown } | Blob | undefined
  const d = detail && !(detail instanceof Blob) ? detail.detail : undefined
  if (typeof d === 'string') return d
  if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg).replace(/^Value error, /, '')
  return fallback
}

/** Blob responses hide the JSON error body; read it back for the message. */
export const blobErrorText = async (e: unknown, fallback: string): Promise<string> => {
  const data = (e as { response?: { data?: unknown } })?.response?.data
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text())
      if (typeof parsed.detail === 'string') return parsed.detail
    } catch { /* not JSON */ }
  }
  return errorText(e, fallback)
}

export const fmtDate = (v?: string | null, withTime = false) => {
  if (!v) return '–'
  const d = new Date(v)
  return withTime
    ? d.toLocaleString('en-NG', { dateStyle: 'medium', timeStyle: 'short' })
    : d.toLocaleDateString('en-NG', { dateStyle: 'medium' })
}

export const nairaToKobo = (v: string) => Math.round(parseFloat(v.replace(/[^\d.]/g, '')) * 100)

export function useDebounced<T>(value: T, ms = 350): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

export const PageHeader: React.FC<{ title: string; subtitle?: string; actions?: React.ReactNode }> = ({ title, subtitle, actions }) => (
  <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={1.5} sx={{ mb: 2.5 }}>
    <Box>
      <Typography variant="h5" fontWeight={800}>{title}</Typography>
      {subtitle && <Typography variant="body2" color="text.secondary">{subtitle}</Typography>}
    </Box>
    {actions && <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>{actions}</Stack>}
  </Stack>
)

export const StatCard: React.FC<{ label: string; value: React.ReactNode; hint?: React.ReactNode; tone?: 'default' | 'good' | 'warn' | 'bad' }> = ({
  label, value, hint, tone = 'default',
}) => {
  const color = { default: 'text.primary', good: 'success.main', warn: 'warning.dark', bad: 'error.main' }[tone]
  return (
    <Paper elevation={0} sx={{ p: 2, border: '1px solid', borderColor: 'grey.200', height: '100%' }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="h5" fontWeight={800} sx={{ color, mt: 0.5 }}>{value}</Typography>
      {hint && <Typography variant="caption" color="text.secondary">{hint}</Typography>}
    </Paper>
  )
}

export const SearchBox: React.FC<{ value: string; onChange: (v: string) => void; placeholder: string }> = ({ value, onChange, placeholder }) => (
  <TextField
    size="small"
    value={value}
    onChange={(e) => onChange(e.target.value)}
    placeholder={placeholder}
    sx={{ minWidth: { xs: '100%', sm: 280 } }}
    InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
  />
)

export const FilterSelect: React.FC<{
  label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[]
}> = ({ label, value, onChange, options }) => (
  <TextField select size="small" label={label} value={value} onChange={(e) => onChange(e.target.value)} sx={{ minWidth: 140 }}>
    <MenuItem value="">All</MenuItem>
    {options.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
  </TextField>
)

export const StatusChip: React.FC<{ status: string }> = ({ status }) => {
  const color = ({
    success: 'success', active: 'success', sponsored: 'success', paid: 'success', free: 'default',
    pending: 'warning', pending_payment: 'warning', failed: 'error', abandoned: 'default', voided: 'error', inactive: 'default',
  } as Record<string, 'success' | 'warning' | 'error' | 'default'>)[status] || 'default'
  return <Chip size="small" color={color} label={status.replace(/_/g, ' ')} variant={color === 'default' ? 'outlined' : 'filled'} />
}

/** Promise-style confirm: `if (await confirm({...})) doIt()` */
type ConfirmOpts = { title: string; body: React.ReactNode; confirmLabel?: string; danger?: boolean; reason?: boolean }
export function useConfirm() {
  const [state, setState] = useState<(ConfirmOpts & { resolve: (v: string | false) => void }) | null>(null)
  const [reason, setReason] = useState('')
  const ask = (opts: ConfirmOpts) => new Promise<string | false>((resolve) => { setReason(''); setState({ ...opts, resolve }) })
  const close = (v: string | false) => { state?.resolve(v); setState(null) }
  const dialog = (
    <Dialog open={!!state} onClose={() => close(false)} maxWidth="xs" fullWidth>
      <DialogTitle>{state?.title}</DialogTitle>
      <DialogContent>
        <DialogContentText component="div">{state?.body}</DialogContentText>
        {state?.reason && (
          <TextField autoFocus fullWidth label="Reason (kept in the audit log)" value={reason}
            onChange={(e) => setReason(e.target.value)} sx={{ mt: 2 }} />
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={() => close(false)}>Cancel</Button>
        <Button
          variant="contained"
          color={state?.danger ? 'error' : 'primary'}
          disabled={!!state?.reason && reason.trim().length < 3}
          onClick={() => close(reason.trim() || 'yes')}
        >
          {state?.confirmLabel || 'Confirm'}
        </Button>
      </DialogActions>
    </Dialog>
  )
  return { confirm: ask, confirmDialog: dialog }
}

/** One place for success / error toasts on a page. */
export function useNotice() {
  const [msg, setMsg] = useState<{ text: string; severity: 'success' | 'error' | 'info' } | null>(null)
  const node = (
    <Snackbar open={!!msg} autoHideDuration={msg?.severity === 'error' ? 8000 : 5000} onClose={() => setMsg(null)}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
      {msg ? <Alert severity={msg.severity} onClose={() => setMsg(null)} variant="filled" sx={{ maxWidth: 560, wordBreak: 'break-word' }}>{msg.text}</Alert> : undefined}
    </Snackbar>
  )
  return {
    ok: (text: string) => setMsg({ text, severity: 'success' }),
    fail: (text: string) => setMsg({ text, severity: 'error' }),
    info: (text: string) => setMsg({ text, severity: 'info' }),
    notice: node,
  }
}

export const copyText = async (text: string): Promise<boolean> => {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

/**
 * Download a certificate PDF, or make a share link anyone can open until it
 * expires. Used by the admin pages and the sponsor portal (different fetchers).
 */
export const CertificateActions: React.FC<{
  certificateId: string
  unpaid?: boolean
  fetchPdf: (id: string) => Promise<Blob>
  makeLink: (id: string, days: number, allowUnpaid: boolean) => Promise<ShareLink>
  compact?: boolean
}> = ({ certificateId, unpaid = false, fetchPdf, makeLink, compact = false }) => {
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)
  const [days, setDays] = useState(7)
  const [allowUnpaid, setAllowUnpaid] = useState(false)
  const [link, setLink] = useState<ShareLink | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const download = async () => {
    setBusy(true)
    setError(null)
    try {
      saveBlob(await fetchPdf(certificateId), `MNAIR-certificate-${certificateId}.pdf`)
    } catch (e) {
      setError(await blobErrorText(e, 'Could not download the certificate.'))
      setOpen(true)
    } finally {
      setBusy(false)
    }
  }

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const l = await makeLink(certificateId, days, allowUnpaid)
      setLink(l)
      setCopied(await copyText(l.url))
    } catch (e) {
      setError(errorText(e, 'Could not create a link.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Stack direction="row" spacing={0.5} alignItems="center">
        {compact ? (
          <>
            <Tooltip title="Download PDF"><span><IconButton size="small" onClick={download} disabled={busy}>
              {busy ? <CircularProgress size={16} /> : <DownloadIcon fontSize="small" />}
            </IconButton></span></Tooltip>
            <Tooltip title="Share link"><IconButton size="small" onClick={() => { setLink(null); setError(null); setOpen(true) }}>
              <LinkIcon fontSize="small" />
            </IconButton></Tooltip>
          </>
        ) : (
          <>
            <Button size="small" variant="outlined" startIcon={busy ? <CircularProgress size={14} /> : <DownloadIcon />} onClick={download} disabled={busy}>
              Download PDF
            </Button>
            <Button size="small" startIcon={<LinkIcon />} onClick={() => { setLink(null); setError(null); setOpen(true) }}>
              Share link
            </Button>
          </>
        )}
      </Stack>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Certificate {certificateId}</DialogTitle>
        <DialogContent>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Anyone with the link can open the PDF without signing in, until it expires. Send it to the learner on
            Telegram, SMS or email.
          </Typography>
          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
            <TextField select size="small" label="Valid for" value={days} onChange={(e) => setDays(Number(e.target.value))} sx={{ width: 140 }}>
              {[1, 3, 7, 14, 30].map((d) => <MenuItem key={d} value={d}>{d} day{d > 1 ? 's' : ''}</MenuItem>)}
            </TextField>
            {unpaid && (
              <FormControlLabel
                control={<Checkbox checked={allowUnpaid} onChange={(e) => setAllowUnpaid(e.target.checked)} />}
                label="Awaiting payment — share anyway"
              />
            )}
            <Button variant="contained" onClick={create} disabled={busy || (unpaid && !allowUnpaid)}>Create link</Button>
          </Stack>
          {link && (
            <Box sx={{ mt: 2 }}>
              <TextField
                fullWidth size="small" value={link.url} InputProps={{
                  readOnly: true,
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton size="small" onClick={async () => setCopied(await copyText(link.url))}><CopyIcon fontSize="small" /></IconButton>
                    </InputAdornment>
                  ),
                }}
              />
              <Typography variant="caption" color={copied ? 'success.main' : 'text.secondary'}>
                {copied ? 'Copied. ' : ''}Expires {fmtDate(link.expires_at, true)}.
              </Typography>
            </Box>
          )}
        </DialogContent>
        <DialogActions><Button onClick={() => setOpen(false)}>Close</Button></DialogActions>
      </Dialog>
    </>
  )
}

export const Loading: React.FC = () => (
  <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress /></Box>
)
