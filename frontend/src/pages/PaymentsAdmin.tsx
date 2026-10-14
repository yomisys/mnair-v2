import React, { useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import {
  Alert, Box, Button, Grid, LinearProgress, Link, Paper, Stack, Table, TableBody, TableCell, TableHead, TablePagination,
  TableRow, TextField, Tooltip, Typography,
} from '@mui/material'
import { Download as DownloadIcon } from '@mui/icons-material'
import { adminAPI, AdminPayment, formatNaira } from '../services/api'
import { exportCSV } from '../components/ExportButton'
import {
  errorText, FilterSelect, fmtDate, PageHeader, SearchBox, StatCard, StatusChip, useConfirm, useDebounced, useNotice,
} from '../components/AdminKit'

/**
 * Admin: every payment — Paystack (sponsors and learners) and bank
 * transfers recorded by hand — with totals for the current filter. A
 * mis-recorded transfer can be voided (reason kept in the audit log).
 */

const PURPOSES = [
  { value: 'sponsor', label: 'All sponsor payments' }, { value: 'sponsor_deposit', label: 'Sponsor deposit' },
  { value: 'sponsor_balance', label: 'Sponsor balance' }, { value: 'sponsor_manual', label: 'Bank transfer (manual)' },
  { value: 'certificate', label: 'Learner certificate' },
]
const STATUSES = ['success', 'pending', 'failed', 'abandoned', 'voided'].map((s) => ({ value: s, label: s }))

const PaymentsAdmin: React.FC = () => {
  const [q, setQ] = useState('')
  const debouncedQ = useDebounced(q)
  const [purpose, setPurpose] = useState('')
  const [status, setStatus] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(0)
  const [perPage, setPerPage] = useState(50)
  const [rows, setRows] = useState<AdminPayment[]>([])
  const [total, setTotal] = useState(0)
  const [totals, setTotals] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const { confirm, confirmDialog } = useConfirm()
  const { ok, fail, notice } = useNotice()

  const filters = {
    q: debouncedQ, purpose, status,
    date_from: from ? `${from}T00:00:00` : undefined,
    // inclusive end date
    date_to: to ? new Date(Date.parse(`${to}T00:00:00Z`) + 86400000).toISOString().slice(0, 19) : undefined,
  }

  useEffect(() => { setPage(0) }, [debouncedQ, purpose, status, from, to])
  useEffect(() => {
    let live = true
    setLoading(true)
    adminAPI.payments({ ...filters, offset: page * perPage, limit: perPage })
      .then((r) => { if (live) { setRows(r.items); setTotal(r.total); setTotals(r.totals_kobo); setError(null) } })
      .catch((e) => live && setError(errorText(e, 'Could not load payments.')))
      .finally(() => live && setLoading(false))
    return () => { live = false }
  }, [debouncedQ, purpose, status, from, to, page, perPage, reload]) // eslint-disable-line react-hooks/exhaustive-deps

  const voidIt = async (p: AdminPayment) => {
    const reason = await confirm({
      title: `Void ${formatNaira(p.amount_kobo)} from ${p.organization_name || p.email}?`,
      body: 'The transfer stops counting toward the sponsor’s balance. Use this only for an entry recorded by mistake.',
      confirmLabel: 'Void payment', danger: true, reason: true,
    })
    if (!reason) return
    try {
      await adminAPI.voidPayment(p.reference, reason)
      ok('Payment voided.')
      setReload((n) => n + 1)
    } catch (e) {
      fail(errorText(e, 'Could not void the payment.'))
    }
  }

  const exportAll = async () => {
    try {
      const r = await adminAPI.payments({ ...filters, offset: 0, limit: 500 })
      exportCSV('mnair-payments.csv', r.items.map((p) => ({
        date: p.paid_at || p.created_at, reference: p.reference, purpose: p.purpose, status: p.status,
        amount_naira: p.amount_kobo / 100, sponsor: p.organization_name || '', learner: p.user_name || '',
        email: p.email, channel: p.channel || '', note: p.note || '',
      })))
      if (r.total > 500) ok(`Exported the latest 500 of ${r.total}. Narrow the dates to export the rest.`)
    } catch (e) {
      fail(errorText(e, 'Export failed.'))
    }
  }

  return (
    <Box sx={{ p: 3 }}>
      <PageHeader title="Payments" subtitle="All money in: Paystack and recorded bank transfers."
        actions={<Button variant="outlined" startIcon={<DownloadIcon />} onClick={exportAll}>Export CSV</Button>} />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><StatCard label="Successful (this filter)" value={formatNaira(totals.success || 0)} tone="good" /></Grid>
        <Grid item xs={6} md={3}><StatCard label="Pending" value={formatNaira(totals.pending || 0)} tone={totals.pending ? 'warn' : 'default'} /></Grid>
        <Grid item xs={6} md={3}><StatCard label="Failed / abandoned" value={formatNaira((totals.failed || 0) + (totals.abandoned || 0))} /></Grid>
        <Grid item xs={6} md={3}><StatCard label="Voided" value={formatNaira(totals.voided || 0)} /></Grid>
      </Grid>

      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        <SearchBox value={q} onChange={setQ} placeholder="Reference, email or note" />
        <FilterSelect label="Type" value={purpose} onChange={setPurpose} options={PURPOSES} />
        <FilterSelect label="Status" value={status} onChange={setStatus} options={STATUSES} />
        <TextField size="small" type="date" label="From" value={from} onChange={(e) => setFrom(e.target.value)} InputLabelProps={{ shrink: true }} />
        <TextField size="small" type="date" label="To" value={to} onChange={(e) => setTo(e.target.value)} InputLabelProps={{ shrink: true }} />
      </Stack>

      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'grey.200', overflowX: 'auto' }}>
        {loading && <LinearProgress />}
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Date</TableCell><TableCell>Payer</TableCell><TableCell>Type</TableCell>
              <TableCell align="right">Amount</TableCell><TableCell>Status</TableCell><TableCell>Reference / note</TableCell><TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {!loading && rows.length === 0 && (
              <TableRow><TableCell colSpan={7} align="center" sx={{ py: 5, color: 'text.secondary' }}>No payments match.</TableCell></TableRow>
            )}
            {rows.map((p) => (
              <TableRow key={p.reference} hover>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{fmtDate(p.paid_at || p.created_at, true)}</TableCell>
                <TableCell>
                  {p.organization_id
                    ? <Link component={RouterLink} to={`/dashboard/sponsors/${p.organization_id}`}>{p.organization_name}</Link>
                    : p.user_id ? <Link component={RouterLink} to={`/dashboard/learners/${p.user_id}`}>{p.user_name || p.email}</Link> : p.email}
                </TableCell>
                <TableCell>{p.purpose.replace(/_/g, ' ')}{p.channel ? <Typography variant="caption" display="block" color="text.secondary">{p.channel}</Typography> : null}</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700 }}>{formatNaira(p.amount_kobo)}</TableCell>
                <TableCell><StatusChip status={p.status} /></TableCell>
                <TableCell sx={{ maxWidth: 280 }}>
                  <Typography variant="caption" display="block">{p.reference}</Typography>
                  {p.note && <Typography variant="caption" color="text.secondary" display="block" sx={{ wordBreak: 'break-word' }}>{p.note}</Typography>}
                  {p.gateway_response && p.status !== 'success' && <Typography variant="caption" color="error.main" display="block">{p.gateway_response}</Typography>}
                </TableCell>
                <TableCell>
                  {p.purpose === 'sponsor_manual' && p.status === 'success' && (
                    <Tooltip title="Reverse a transfer recorded by mistake"><Button size="small" color="error" onClick={() => voidIt(p)}>Void</Button></Tooltip>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <TablePagination component="div" count={total} page={page} rowsPerPage={perPage} rowsPerPageOptions={[25, 50, 100, 200]}
          onPageChange={(_, n) => setPage(n)} onRowsPerPageChange={(e) => { setPerPage(Number(e.target.value)); setPage(0) }} />
      </Paper>
      {confirmDialog}
      {notice}
    </Box>
  )
}

export default PaymentsAdmin
