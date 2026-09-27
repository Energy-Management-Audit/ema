import { useEffect } from 'react'
import { navigate } from '../../app/navigate.ts'
import { auditHref, type AuditTab } from '../../app/route.ts'
import { ReadingsScreen } from '../ReadingsScreen.tsx'
import { AuditExportScreen } from './AuditExportScreen.tsx'
import { ReportScreen } from './ReportScreen.tsx'

export type AuditJobScreenProps = { jobId: string; tab: AuditTab; field: string | null }

export function AuditJobScreen({ jobId, tab, field }: AuditJobScreenProps) {
  useEffect(() => {
    if (tab !== 'masuratori' && tab !== 'raport' && tab !== 'predare') {
      navigate(auditHref(jobId, 'masuratori'), true)
    }
  }, [jobId, tab])
  if (tab === 'masuratori') return <ReadingsScreen jobId={jobId} field={field} />
  if (tab === 'raport') return <ReportScreen jobId={jobId} />
  if (tab === 'predare') return <AuditExportScreen jobId={jobId} />
  return null
}
