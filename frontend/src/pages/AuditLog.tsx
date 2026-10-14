import React, { useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import {
  Alert, Box, Collapse, IconButton, LinearProgress, Link, Paper, Stack, Table, TableBody, TableCell, TableHead,
  TablePagination, TableRow, Typography,
} from '@mui/material'
import { KeyboardArrowDown as OpenIcon, KeyboardArrowUp as CloseIcon } from '@mui/icons-material'
import { adminAPI, AuditEntry } from '../services/api'
import { errorText, FilterSelect, fmtDate, PageHeader, SearchBox, useDebounced } from '../components/AdminKit'

/** Admin: who changed what, when. Append-only; passwords never appear. */

const targetLink = (a: AuditEntry) => {
  if (!a.target_id) return null
  if (a.target_type === 'sponsor') return <Link component={RouterLink} to={`/dashboard/sponsors/${a.target_id}`}>sponsor #{a.target_id}</Link>
  if (a.target_type === 'learner') return <Link component={RouterLink} to={`/dashboard/learners/${a.target_id}`}>learner #{a.target_id}</Link>
  return <span>{a.target_type} {a.target_id}</span>
}

const Entry: React.FC<{ a: AuditEntry }> = ({ a }) => {
  const [open, setOpen] = useState(false)
  return (
    <>
      <TableRow hover>
        <TableCell sx={{ width: 40 }}>
          {a.details && <IconButton size="small" onClick={() => setOpen(!open)}>{open ? <CloseIcon fontSize="small" /> : <OpenIcon fontSize="small" />}</IconButton>}
        </TableCell>
        <TableCell sx={{ whiteSpace: 'nowrap' }}>{fmtDate(a.created_at, true)}</TableCell>
        <TableCell>{a.admin}</TableCell>
        <TableCell><Typography variant="caption" sx={{ fontFamily: 'monospace' }}>{a.action}</Typography></TableCell>
        <TableCell>{a.summary}</TableCell>
        <TableCell>{targetLink(a)}</TableCell>
      </TableRow>
      {a.details && (
        <TableRow>
          <TableCell colSpan={6} sx={{ py: 0, borderBottom: open ? undefined : 'none' }}>
            <Collapse in={open} unmountOnExit>
              <Box component="pre" sx={{ m: 1, p: 1.5, bgcolor: 'grey.50', borderRadius: 1, fontSize: 12, overflowX: 'auto' }}>
                {JSON.stringify(a.details, null, 2)}
              </Box>
              {a.ip_address && <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>From {a.ip_address}</Typography>}
            </Collapse>
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

const AuditLog: React.FC = () => {
  const [q, setQ] = useState('')
  const debouncedQ = useDebounced(q)
  const [action, setAction] = useState('')
  const [actions, setActions] = useState<string[]>([])
  const [page, setPage] = useState(0)
  const [perPage, setPerPage] = useState(50)
  const [rows, setRows] = useState<AuditEntry[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { setPage(0) }, [debouncedQ, action])
  useEffect(() => {
    let live = true
    setLoading(true)
    adminAPI.audit({ q: debouncedQ, action, offset: page * perPage, limit: perPage })
      .then((r) => { if (live) { setRows(r.items); setTotal(r.total); setActions(r.actions); setError(null) } })
      .catch((e) => live && setError(errorText(e, 'Could not load the audit log.')))
      .finally(() => live && setLoading(false))
    return () => { live = false }
  }, [debouncedQ, action, page, perPage])

  const groups = Array.from(new Set(actions.map((a) => a.split('.')[0] + '.')))
  return (
    <Box sx={{ p: 3 }}>
      <PageHeader title="Audit log" subtitle="Every change made in this admin panel. Entries can't be edited or deleted." />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        <SearchBox value={q} onChange={setQ} placeholder="Search summary or admin name" />
        <FilterSelect label="Action" value={action} onChange={setAction}
          options={[...groups.map((g) => ({ value: g, label: `All ${g.slice(0, -1)}` })), ...actions.map((a) => ({ value: a, label: a }))]} />
      </Stack>
      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'grey.200', overflowX: 'auto' }}>
        {loading && <LinearProgress />}
        <Table size="small">
          <TableHead>
            <TableRow><TableCell /><TableCell>When</TableCell><TableCell>Admin</TableCell><TableCell>Action</TableCell><TableCell>What</TableCell><TableCell>Target</TableCell></TableRow>
          </TableHead>
          <TableBody>
            {!loading && rows.length === 0 && (
              <TableRow><TableCell colSpan={6} align="center" sx={{ py: 5, color: 'text.secondary' }}>Nothing logged yet.</TableCell></TableRow>
            )}
            {rows.map((a) => <Entry key={a.id} a={a} />)}
          </TableBody>
        </Table>
        <TablePagination component="div" count={total} page={page} rowsPerPage={perPage} rowsPerPageOptions={[25, 50, 100]}
          onPageChange={(_, n) => setPage(n)} onRowsPerPageChange={(e) => { setPerPage(Number(e.target.value)); setPage(0) }} />
      </Paper>
    </Box>
  )
}

export default AuditLog
