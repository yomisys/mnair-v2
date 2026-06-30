import React from 'react'
import { Button } from '@mui/material'
import { Download as DownloadIcon } from '@mui/icons-material'

export function exportCSV(filename: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return
  const headers = Object.keys(rows[0])
  const csv = [
    headers.join(','),
    ...rows.map(r =>
      headers.map(h => {
        const v = r[h]
        if (v === null || v === undefined) return ''
        const s = String(v)
        return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s
      }).join(',')
    ),
  ].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const ExportButton: React.FC<{ data: Record<string, unknown>[]; filename: string }> = ({ data, filename }) => (
  <Button
    variant="outlined"
    size="small"
    startIcon={<DownloadIcon />}
    onClick={() => exportCSV(filename, data)}
    disabled={!data.length}
  >
    Export CSV
  </Button>
)

export default ExportButton
