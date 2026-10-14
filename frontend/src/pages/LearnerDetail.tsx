import React, { useEffect, useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'
import {
  Alert, Box, Breadcrumbs, Button, Dialog, DialogActions, DialogContent, DialogTitle, Grid, Link, MenuItem, Paper,
  Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography,
} from '@mui/material'
import { adminAPI, AdminLearnerDetail, formatNaira } from '../services/api'
import {
  CertificateActions, errorText, fmtDate, Loading, PageHeader, StatCard, StatusChip, useConfirm, useNotice,
} from '../components/AdminKit'

/**
 * Admin: one learner. Fix their details (new SIM, name typo), reset a
 * forgotten PIN, deactivate, detach from a sponsor, and download or share
 * their certificate. Every change lands in the audit log shown at the bottom.
 */

const LANGS = [['en', 'English'], ['pid', 'Pidgin'], ['ha', 'Hausa'], ['yo', 'Yoruba'], ['ig', 'Igbo']]

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <Stack direction="row" spacing={2} sx={{ py: 0.75, borderBottom: '1px solid', borderColor: 'grey.100' }}>
    <Typography variant="body2" color="text.secondary" sx={{ width: 150, flexShrink: 0 }}>{label}</Typography>
    <Typography variant="body2" component="div" sx={{ wordBreak: 'break-word' }}>{children}</Typography>
  </Stack>
)

const LearnerDetail: React.FC = () => {
  const id = Number(useParams().id)
  const [data, setData] = useState<AdminLearnerDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [edit, setEdit] = useState<Record<string, string> | null>(null)
  const [saving, setSaving] = useState(false)
  const { confirm, confirmDialog } = useConfirm()
  const { ok, fail, notice } = useNotice()

  const load = () => adminAPI.learner(id).then(setData).catch((e) => setError(errorText(e, 'Could not load this learner.')))
  useEffect(() => { load() }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <Box sx={{ p: 3 }}><Alert severity="error">{error}</Alert></Box>
  if (!data) return <Loading />

  const isChatIdentity = data.phone_number.startsWith('tg:') || data.phone_number.startsWith('kc:')

  const act = async (fn: () => Promise<unknown>, success: string) => {
    try {
      await fn()
      ok(success)
      load()
    } catch (e) {
      fail(errorText(e, 'That did not work.'))
    }
  }

  const openEdit = () => setEdit({
    name: data.name, phone_number: isChatIdentity ? '' : data.phone_number, email: data.email || '',
    language: data.language, role: data.role, password: '',
  })

  const save = async () => {
    if (!edit) return
    const body: Record<string, unknown> = {}
    if (edit.name !== data.name) body.name = edit.name
    if (!isChatIdentity && edit.phone_number && edit.phone_number !== data.phone_number) body.phone_number = edit.phone_number
    if ((edit.email || '') !== (data.email || '')) body.email = edit.email
    if (edit.language !== data.language) body.language = edit.language
    if (edit.role !== data.role) body.role = edit.role
    if (edit.password) body.password = edit.password
    if (!Object.keys(body).length) { setEdit(null); return }
    if (body.role && !(await confirm({
      title: 'Change role?',
      body: body.role === 'admin'
        ? `${data.name} will be able to sign in to this admin panel and change anything here.`
        : `${data.name} will lose ${data.role} access.`,
      confirmLabel: 'Change role', danger: body.role === 'admin',
    }))) return
    setSaving(true)
    try {
      await adminAPI.updateLearner(id, body)
      ok('Saved.')
      setEdit(null)
      load()
    } catch (e) {
      fail(errorText(e, 'Could not save.'))
    } finally {
      setSaving(false)
    }
  }

  const toggleActive = async () => {
    const deactivate = data.is_active
    if (!(await confirm({
      title: deactivate ? 'Deactivate this account?' : 'Reactivate this account?',
      body: deactivate
        ? 'They will not be able to sign in or receive lessons until reactivated. Their progress is kept.'
        : 'They will be able to sign in and continue where they stopped.',
      confirmLabel: deactivate ? 'Deactivate' : 'Reactivate', danger: deactivate,
    }))) return
    act(() => adminAPI.updateLearner(id, { is_active: !deactivate }), deactivate ? 'Account deactivated.' : 'Account reactivated.')
  }

  const resetPin = async () => {
    if (!(await confirm({
      title: 'Reset web PIN?',
      body: <>The current PIN stops working. Tell {data.name} to open <b>/learn</b>, enter their phone number and
        choose a <b>new PIN</b> — it is set on that sign-in. Progress is not affected.</>,
      confirmLabel: 'Reset PIN',
    }))) return
    act(() => adminAPI.resetPin(id), 'PIN cleared. The learner sets a new one on their next sign-in.')
  }

  const removeSponsor = async () => {
    if (!data.sponsor) return
    if (!(await confirm({
      title: `Remove from ${data.sponsor.name}?`,
      body: 'Use this when the learner enrolled with the wrong code. A certificate already billed stays on the sponsor\'s invoice.',
      confirmLabel: 'Remove', danger: true,
    }))) return
    act(() => adminAPI.removeSponsor(id), 'Removed from sponsor.')
  }

  const p = data.progress
  return (
    <Box sx={{ p: 3 }}>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/dashboard/learners" underline="hover">Learners</Link>
        <Typography color="text.primary">{data.name}</Typography>
      </Breadcrumbs>
      <PageHeader
        title={data.name}
        subtitle={`#${data.id} · ${data.role} · joined ${fmtDate(data.created_at)}`}
        actions={<>
          <Button variant="contained" onClick={openEdit}>Edit details</Button>
          {data.role === 'learner' && <Button variant="outlined" onClick={resetPin}>Reset PIN</Button>}
          <Button variant="outlined" color={data.is_active ? 'error' : 'success'} onClick={toggleActive}>
            {data.is_active ? 'Deactivate' : 'Reactivate'}
          </Button>
        </>}
      />

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><StatCard label="Days completed" value={`${data.completed_days}/7`} hint={`Currently on day ${data.current_day}`} tone={data.completed_days >= 7 ? 'good' : 'default'} /></Grid>
        <Grid item xs={6} md={3}><StatCard label="Lessons completed" value={p.lessons_completed} /></Grid>
        <Grid item xs={6} md={3}><StatCard label="Quiz accuracy" value={p.quiz_accuracy != null ? `${p.quiz_accuracy}%` : '–'} hint={`${p.quiz_correct}/${p.quiz_questions} correct over ${p.quiz_attempts} attempts`} /></Grid>
        <Grid item xs={6} md={3}><StatCard label="Status" value={<StatusChip status={data.is_active ? 'active' : 'inactive'} />} hint={`Last active ${fmtDate(data.last_active_at, true)}`} /></Grid>
      </Grid>

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Paper elevation={0} sx={{ p: 2, border: '1px solid', borderColor: 'grey.200', height: '100%' }}>
            <Typography fontWeight={700} sx={{ mb: 1 }}>Account</Typography>
            <Row label="Phone / identity">{data.phone_number}{isChatIdentity && ' (chat identity)'}</Row>
            <Row label="Email">{data.email || '–'}</Row>
            <Row label="Language">{data.language.toUpperCase()}</Row>
            <Row label="Channel">{data.preferred_channel || '–'}{data.telegram_linked ? ' · Telegram linked' : ''}</Row>
            <Row label="Web PIN">{data.has_pin ? 'Set' : 'Not set — chosen on next /learn sign-in'}</Row>
            {data.role !== 'learner' && <Row label="Admin password">{data.has_password ? 'Set' : 'Not set'}</Row>}
            <Row label="Network">{data.network_operator || '–'}</Row>
            <Row label="Consent">{data.consent_given ? `Given ${fmtDate(data.consent_date)}` : 'Not given'}</Row>
            <Row label="Name confirmed">{data.name_confirmed ? 'Yes' : 'No — certificate waits for it'}</Row>
          </Paper>
        </Grid>
        <Grid item xs={12} md={6}>
          <Paper elevation={0} sx={{ p: 2, border: '1px solid', borderColor: 'grey.200', mb: 2 }}>
            <Typography fontWeight={700} sx={{ mb: 1 }}>Sponsor</Typography>
            {data.sponsor ? (
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Box>
                  <Link component={RouterLink} to={`/dashboard/sponsors/${data.sponsor.id}`}>{data.sponsor.name}</Link>
                  <Typography variant="caption" display="block" color="text.secondary">
                    Code {data.sponsor.code} · since {fmtDate(data.sponsor.sponsored_at)}
                  </Typography>
                </Box>
                <Button size="small" color="error" onClick={removeSponsor}>Remove</Button>
              </Stack>
            ) : <Typography variant="body2" color="text.secondary">Not sponsored.</Typography>}
          </Paper>
          <Paper elevation={0} sx={{ p: 2, border: '1px solid', borderColor: 'grey.200' }}>
            <Typography fontWeight={700} sx={{ mb: 1 }}>Certificate</Typography>
            {data.certificates.length === 0 && <Typography variant="body2" color="text.secondary">Not issued yet — issued when all 7 days are complete.</Typography>}
            {data.certificates.map((c) => (
              <Box key={c.certificate_id} sx={{ mb: 1.5 }}>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                  <Typography fontWeight={600}>{c.certificate_id}</Typography>
                  <StatusChip status={c.access_type} />
                </Stack>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                  Issued {fmtDate(c.issued_at)} · name on certificate “{c.learner_name}”
                  {c.average_quiz_score != null ? ` · avg quiz ${Math.round(c.average_quiz_score)}%` : ''}
                  {c.sponsor_name ? ` · sponsored by ${c.sponsor_name}` : ''}
                </Typography>
                <CertificateActions
                  certificateId={c.certificate_id}
                  unpaid={!c.is_verified}
                  fetchPdf={adminAPI.certificatePdf}
                  makeLink={(cid, days, allow) => adminAPI.certificateLink(cid, days, allow)}
                />
              </Box>
            ))}
          </Paper>
        </Grid>
      </Grid>

      {data.payments.length > 0 && (
        <Paper elevation={0} sx={{ p: 2, border: '1px solid', borderColor: 'grey.200', mt: 2, overflowX: 'auto' }}>
          <Typography fontWeight={700} sx={{ mb: 1 }}>Payments</Typography>
          <Table size="small">
            <TableHead><TableRow><TableCell>Date</TableCell><TableCell>Reference</TableCell><TableCell>Purpose</TableCell><TableCell align="right">Amount</TableCell><TableCell>Status</TableCell></TableRow></TableHead>
            <TableBody>
              {data.payments.map((x) => (
                <TableRow key={x.reference}>
                  <TableCell>{fmtDate(x.paid_at || x.created_at, true)}</TableCell><TableCell>{x.reference}</TableCell>
                  <TableCell>{x.purpose}</TableCell><TableCell align="right">{formatNaira(x.amount_kobo)}</TableCell>
                  <TableCell><StatusChip status={x.status} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      <Paper elevation={0} sx={{ p: 2, border: '1px solid', borderColor: 'grey.200', mt: 2 }}>
        <Typography fontWeight={700} sx={{ mb: 1 }}>Admin history</Typography>
        {data.history.length === 0 && <Typography variant="body2" color="text.secondary">No admin changes yet.</Typography>}
        {data.history.map((h) => (
          <Typography key={h.id} variant="body2" sx={{ py: 0.5 }}>
            <Box component="span" color="text.secondary">{fmtDate(h.created_at, true)} · {h.admin}:</Box> {h.summary}
          </Typography>
        ))}
      </Paper>

      <Dialog open={!!edit} onClose={() => setEdit(null)} fullWidth maxWidth="sm">
        <DialogTitle>Edit {data.name}</DialogTitle>
        <DialogContent>
          {edit && (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField label="Full name (printed on the certificate)" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />
              <TextField
                label="Phone number" value={edit.phone_number} disabled={isChatIdentity}
                onChange={(e) => setEdit({ ...edit, phone_number: e.target.value })}
                helperText={isChatIdentity
                  ? 'This learner is identified by their Telegram/KingsChat chat, not a phone number.'
                  : 'For a learner who changed SIM: their progress moves to the new number. Then reset their PIN.'}
              />
              <TextField label="Email" value={edit.email} onChange={(e) => setEdit({ ...edit, email: e.target.value })} />
              <Stack direction="row" spacing={2}>
                <TextField select fullWidth label="Language" value={edit.language} onChange={(e) => setEdit({ ...edit, language: e.target.value })}>
                  {LANGS.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
                </TextField>
                <TextField select fullWidth label="Role" value={edit.role} onChange={(e) => setEdit({ ...edit, role: e.target.value })}>
                  <MenuItem value="learner">Learner</MenuItem><MenuItem value="admin">Admin</MenuItem><MenuItem value="employer">Employer</MenuItem>
                </TextField>
              </Stack>
              {(edit.role === 'admin' || data.role === 'admin') && (
                <TextField type="password" label={data.has_password ? 'New admin password (leave blank to keep)' : 'Admin password (10+ characters)'}
                  value={edit.password} onChange={(e) => setEdit({ ...edit, password: e.target.value })} />
              )}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEdit(null)}>Cancel</Button>
          <Button variant="contained" onClick={save} disabled={saving}>Save</Button>
        </DialogActions>
      </Dialog>
      {confirmDialog}
      {notice}
    </Box>
  )
}

export default LearnerDetail
