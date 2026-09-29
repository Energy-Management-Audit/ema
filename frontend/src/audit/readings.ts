import type { Field, VisitPhoto, VisitView } from '../api/types.ts'

export type ReadingGroup = { id: string; label: string; fields: Field[] }

export function photoForField(field: Field, visit: VisitView): VisitPhoto | null {
  const parts = field.key.split('.')
  if (parts[0] === 'meter' && parts[1] && parts[2]) {
    return (
      visit.panels
        .find((panel) => panel.id === parts[1])
        ?.photos.find((photo) => photo.sha.startsWith(parts[2] ?? '')) ?? null
    )
  }
  if (parts[0] === 'thermal' && parts[1]) {
    return visit.thermal.find((photo) => photo.sha.startsWith(parts[1] ?? '')) ?? null
  }
  return null
}

export function readingGroups(fields: Field[], visit: VisitView): ReadingGroup[] {
  const groups = visit.panels.map((panel) => ({
    id: panel.id,
    label: panel.label,
    fields: fields.filter(
      (field) =>
        field.key.startsWith(`meter.${panel.id}.`) ||
        field.key.startsWith(`narrative.ch5.${panel.id}.`),
    ),
  }))
  const thermal = fields.filter(
    (field) => field.key.startsWith('thermal.') || field.key.startsWith('narrative.ch5.termic'),
  )
  if (visit.thermal.length) groups.push({ id: 'thermal', label: 'Termografiere', fields: thermal })
  const general = fields.filter(
    (field) =>
      field.key === 'visit.date' ||
      ['narrative.ch5.electric_rezultate', 'narrative.ch5.electric_concluzii'].includes(field.key),
  )
  if (general.length) groups.unshift({ id: 'visit', label: 'Vizită', fields: general })
  return groups
}

export function readingLabel(field: Field): string {
  const parts = field.key.split('.')
  if (parts[0] !== 'meter' || parts.length < 5) return field.label
  const quantity = parts.at(-2) ?? ''
  const phase = parts.at(-1) ?? ''
  const names: Record<string, string> = {
    frequency: 'Frecvenţa',
    voltage_ln: 'Tensiunea de fază',
    voltage_ll: 'Tensiunea de linie',
    current: 'Curentul',
    thd_u: 'THD tensiune',
    thd_i: 'THD curent',
    power_active: 'Puterea activă',
    power_reactive: 'Puterea reactivă',
    power_apparent: 'Puterea aparentă',
    power_factor: 'Factorul de putere',
    energy_active: 'Energia activă',
    energy_reactive: 'Energia reactivă',
  }
  if (quantity === 'display') return 'Ecranul report_client_bşat'
  return `${names[quantity] ?? field.label} · ${phase.toUpperCase()}`
}
