import type { AuditDocuments } from '../api/audit-types.ts'

export type NextStage = {
  title: string
  body: string
  action?: string
  stage?: 'intake' | 'read' | 'visit' | 'measures'
  filter?: 'missing'
}

export function nextStage(documents: AuditDocuments): NextStage | null {
  if (!documents.files.some((file) => file.slot.split('/').at(-1)?.startsWith('0.'))) {
    return {
      title: 'Lipseşte Necesar info',
      body: 'Dosarul trebuie să conţină fişierul „0. Necesar info”, ca Ema să ştie ce documente aşteaptă.',
    }
  }
  if (!documents.runs.intake?.current) {
    return {
      title: 'Documentele nu sunt citite',
      body: 'Ema le converteşte, le clasifică după lista de documente şi îţi spune ce lipseşte.',
      action: 'Citeşte dosarul',
      stage: 'intake',
    }
  }
  if (!documents.runs.read?.current) {
    return {
      title: 'Datele nu sunt extrase',
      body: 'Ema citeşte cifrele din Necesar info şi Anexa 2–3; fiecare valoare îşi păstrează celula.',
      action: 'Extrage datele',
      stage: 'read',
    }
  }
  if (documents.visit && !documents.runs.visit?.current) {
    return {
      title: 'Fotografiile din vizită nu sunt înregistrate',
      body: 'Ema le grupează pe tablouri şi pregăteşte citirea valorilor de pe ele.',
      action: 'Înregistrează fotografiile',
      stage: 'visit',
    }
  }
  if (documents.measures && !documents.runs.measures?.current) {
    return {
      title: 'Măsurile propuse nu sunt citite',
      body: 'Ema citeşte formularul şi calculează economia în tep, CO₂ şi durata de recuperare.',
      action: 'Citeşte măsurile',
      stage: 'measures',
    }
  }
  if (documents.missing.length) {
    return {
      title: `Lipsesc documentele ${documents.missing.join(', ')}`,
      body: documents.checklist?.find((item) => item.number === documents.missing[0])?.text ?? '',
      action: 'Vezi lista',
      filter: 'missing',
    }
  }
  return null
}
