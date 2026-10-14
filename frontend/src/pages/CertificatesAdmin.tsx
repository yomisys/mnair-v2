import React, { useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import {
  Alert, Box, LinearProgress, Link, Paper, Stack, Table, TableBody, TableCell, TableHead, TablePagination, TableRow, Typography,
} from '@mui/material'
import { adminAPI, AdminCertificate } from '../services/api'
import { CertificateActions, errorText, FilterSelect, fmtDate, PageHeader, SearchBox, StatusChip, useDebounced } from '../components/AdminKit'

/** Admin: every issued certificate — find by code or name, download or share the PDF. */

const ACCESS = [
  { value: 'free', label: 'Free' }, { value: 'sponsored', label: 'Sponsored' },
  { value: 'paid', label: 'Paid' }, { value: 'pending_payment', label: 'Awaiting payment' },
]

const CertificatesAdmin: React.FC = () => {
  const [q, setQ] = useState('')
  const debouncedQ = useDebounced(q)
  const [access, setAccess] = useState('')
  const [page, setPage] = useState(0)
  const [perPage, setPerPage] = useState(25)
  const [rows, setRows] = useState<AdminCertificate[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { setPage(0) }, [debouncedQ, access])
  useEffect(() => {
    let live = true
    setLoading(true)
    adminAPI.certificates({ q: debouncedQ, access_type: access, offset: page * perPage, limit: perPage })
      .then((r) => { if (live) { setRows(r.items); setTotal(r.total); setError(null) } })
      .catch((e) => live && setError(errorText(e, 'Could not load certificates.')))
      .finally(() => live && setLoading(false))
    return () => { live = false }
  }, [debouncedQ, access, page, perPage])

  return (
    <Box sx={{ p: 3 }}>
      <PageHeader title="Certificates" subtitle={`${total.toLocaleString()} issued. Download a PDF or send a link the learner can open without signing in.`} />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        <SearchBox value={q} onChange={setQ} placeholder="Certificate code or learner name" />
        <FilterSelect label="Access" value={access} onChange={setAccess} options={ACCESS} />
      </Stack>
      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'grey.200', overflowX: 'auto' }}>
        {loading && <LinearProgress />}
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Certificate</TableCell><TableCell>Learner</TableCell><TableCell>Issued</TableCell>
              <TableCell>Access</TableCell><TableCell>Sponsor</TableCell><TableCell align="right">Avg quiz</TableCell><TableCell>PDF</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {!loading && rows.length === 0 && (
              <TableRow><TableCell colSpan={7} align="center" sx={{ py: 5, color: 'text.secondary' }}>No certificates match.</TableCell></TableRow>
            )}
            {rows.map((c) => (
              <TableRow key={c.certificate_id} hover>
                <TableCell><Typography fontWeight={600} variant="body2">{c.certificate_id}</Typography></TableCell>
                <TableCell>{c.user_id ? <Link component={RouterLink} to={`/dashboard/learners/${c.user_id}`}>{c.learner_name}</Link> : c.learner_name}</TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{fmtDate(c.issued_at)}</TableCell>
                <TableCell><StatusChip status={c.access_type} /></TableCell>
                <TableCell>{c.sponsor_name || '–'}</TableCell>
                <TableCell align="right">{c.average_quiz_score != null ? `${Math.round(c.average_quiz_score)}%` : '–'}</TableCell>
                <TableCell>
                  <CertificateActions compact certificateId={c.certificate_id} unpaid={!c.is_verified}
                    fetchPdf={adminAPI.certificatePdf} makeLink={(cid, d, a) => adminAPI.certificateLink(cid, d, a)} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <TablePagination component="div" count={total} page={page} rowsPerPage={perPage} rowsPerPageOptions={[25, 50, 100]}
          onPageChange={(_, p) => setPage(p)} onRowsPerPageChange={(e) => { setPerPage(Number(e.target.value)); setPage(0) }} />
      </Paper>
    </Box>
  )
}

export default CertificatesAdmin
