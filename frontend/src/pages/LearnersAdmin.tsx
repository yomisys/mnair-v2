import React, { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Alert, Box, Chip, LinearProgress, Paper, Stack, Table, TableBody, TableCell, TableHead, TablePagination, TableRow, Typography,
} from '@mui/material'
import { adminAPI, AdminLearnerRow } from '../services/api'
import { errorText, FilterSelect, fmtDate, PageHeader, SearchBox, StatusChip, useDebounced } from '../components/AdminKit'

/**
 * Admin: find any learner (name, phone in any format, email), filter, and
 * open their record. Paged on the server so it stays fast at scale.
 */

const LANGS = [
  { value: 'en', label: 'English' }, { value: 'pid', label: 'Pidgin' }, { value: 'ha', label: 'Hausa' },
  { value: 'yo', label: 'Yoruba' }, { value: 'ig', label: 'Igbo' },
]
const CHANNELS = ['web', 'telegram', 'ussd', 'sms', 'kingschat'].map((c) => ({ value: c, label: c }))
const SORTS = [
  { value: 'newest', label: 'Newest' }, { value: 'last_active', label: 'Last active' },
  { value: 'progress', label: 'Most progress' }, { value: 'name', label: 'Name A–Z' }, { value: 'oldest', label: 'Oldest' },
]

const LearnersAdmin: React.FC = () => {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const get = (k: string, d = '') => params.get(k) ?? d
  const [q, setQ] = useState(get('q'))
  const debouncedQ = useDebounced(q)
  const [rows, setRows] = useState<AdminLearnerRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const page = Number(get('page', '0'))
  const perPage = Number(get('per', '25'))
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params)
    if (v) next.set(k, v); else next.delete(k)
    if (k !== 'page') next.delete('page')
    setParams(next, { replace: true })
  }

  useEffect(() => { if (debouncedQ !== get('q')) set('q', debouncedQ) }, [debouncedQ]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let live = true
    setLoading(true)
    adminAPI.learners({
      q: get('q'), status: get('status'), role: get('role'), language: get('language'), channel: get('channel'),
      certified: get('certified'), sponsor_id: get('sponsor_id'), sort: get('sort', 'newest'),
      offset: page * perPage, limit: perPage,
    })
      .then((r) => { if (live) { setRows(r.items); setTotal(r.total); setError(null) } })
      .catch((e) => live && setError(errorText(e, 'Could not load learners.')))
      .finally(() => live && setLoading(false))
    return () => { live = false }
  }, [params]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Box sx={{ p: 3 }}>
      <PageHeader title="Learners" subtitle={`${total.toLocaleString()} accounts match. Click a row to manage it.`} />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        <SearchBox value={q} onChange={setQ} placeholder="Name, phone (080… or +234…), email" />
        <FilterSelect label="Status" value={get('status')} onChange={(v) => set('status', v)}
          options={[{ value: 'active', label: 'Active' }, { value: 'inactive', label: 'Deactivated' }]} />
        <FilterSelect label="Certificate" value={get('certified')} onChange={(v) => set('certified', v)}
          options={[{ value: 'true', label: 'Certified' }, { value: 'false', label: 'Not yet' }]} />
        <FilterSelect label="Language" value={get('language')} onChange={(v) => set('language', v)} options={LANGS} />
        <FilterSelect label="Channel" value={get('channel')} onChange={(v) => set('channel', v)} options={CHANNELS} />
        <FilterSelect label="Role" value={get('role')} onChange={(v) => set('role', v)}
          options={[{ value: 'learner', label: 'Learner' }, { value: 'admin', label: 'Admin' }, { value: 'employer', label: 'Employer' }]} />
        <FilterSelect label="Sort" value={get('sort')} onChange={(v) => set('sort', v)} options={SORTS} />
        {get('sponsor_id') && <Chip label={`Sponsor #${get('sponsor_id')}`} onDelete={() => set('sponsor_id', '')} />}
      </Stack>

      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'grey.200', overflowX: 'auto' }}>
        {loading && <LinearProgress />}
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Learner</TableCell><TableCell>Phone</TableCell><TableCell>Progress</TableCell>
              <TableCell>Sponsor</TableCell><TableCell>Certificate</TableCell><TableCell>Channel</TableCell>
              <TableCell>Last active</TableCell><TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {!loading && rows.length === 0 && (
              <TableRow><TableCell colSpan={8} align="center" sx={{ py: 5, color: 'text.secondary' }}>No learners match.</TableCell></TableRow>
            )}
            {rows.map((r) => (
              <TableRow key={r.id} hover sx={{ cursor: 'pointer' }} onClick={() => navigate(`/dashboard/learners/${r.id}`)}>
                <TableCell>
                  <Typography fontWeight={600}>{r.name}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    #{r.id} · {r.language.toUpperCase()}{r.role !== 'learner' ? ` · ${r.role}` : ''}{!r.name_confirmed ? ' · name unconfirmed' : ''}
                  </Typography>
                </TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{r.phone_number}</TableCell>
                <TableCell sx={{ minWidth: 110 }}>
                  <Typography variant="body2">{r.completed_days}/7 days</Typography>
                  <LinearProgress variant="determinate" value={(r.completed_days / 7) * 100} sx={{ height: 5, borderRadius: 3 }}
                    color={r.completed_days >= 7 ? 'success' : 'primary'} />
                </TableCell>
                <TableCell>{r.sponsor ? <><Typography variant="body2">{r.sponsor.name}</Typography><Typography variant="caption" color="text.secondary">{r.sponsor.code}</Typography></> : '–'}</TableCell>
                <TableCell>{r.certificate_id ? <StatusChip status={r.certificate_access || 'free'} /> : '–'}</TableCell>
                <TableCell>{r.preferred_channel || '–'}</TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{fmtDate(r.last_active_at)}</TableCell>
                <TableCell><StatusChip status={r.is_active ? 'active' : 'inactive'} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <TablePagination
          component="div" count={total} page={page} rowsPerPage={perPage} rowsPerPageOptions={[25, 50, 100]}
          onPageChange={(_, p) => set('page', String(p))}
          onRowsPerPageChange={(e) => { const next = new URLSearchParams(params); next.set('per', e.target.value); next.delete('page'); setParams(next, { replace: true }) }}
        />
      </Paper>
    </Box>
  )
}

export default LearnersAdmin
