// Display labels (D7). Enum values stay English in the data; Romanian lives only here.

export const CARRIERS: Record<string, string> = {
  electricity_grid: 'Energie electrică din SEN',
  electricity_pv: 'Energie electrică din parcul fotovoltaic propriu',
  natural_gas: 'Gaz natural',
  diesel: 'Motorină',
  petrol: 'Benzină',
  lpg: 'GPL',
  fuel_oil: 'Păcură',
  clu: 'Combustibil lichid uşor',
  coal: 'Cărbune',
  coke: 'Cocs',
  wood: 'Lemn',
  biomass: 'Biomasă',
  sunflower_husks: 'Coji de floarea-soarelui',
  biogas: 'Biogaz',
  ctl: 'CTL',
  purchased_heat: 'Energie termică de la terţi',
  water_potable: 'Apă potabilă',
  water_industrial: 'Apă industrială',
  water_storm: 'Apă pluvială',
}

/** The Carrier enum order of `ema.energy_data.carriers`. */
export const CARRIER_ORDER = Object.keys(CARRIERS)

export const MONTHS = [
  'Ian',
  'Feb',
  'Mar',
  'Apr',
  'Mai',
  'Iun',
  'Iul',
  'Aug',
  'Sep',
  'Oct',
  'Noi',
  'Dec',
]

export const MEASURE_COLUMNS: Record<string, string> = {
  description: 'denumire',
  investment_thousand_lei: 'investiţie',
  saving_mwh: 'economie MWh',
  saving_tep: 'economie tep',
  saving_thousand_lei: 'economie mii lei',
  payback_years: 'recuperare',
  commissioning_year: 'termen',
  location: 'loc',
}

const IDENTITY: Record<string, string> = {
  name: 'Denumire',
  cui: 'CUI',
  registrul_comertului: 'Nr. Registrul Comerţului',
  address: 'Sediu',
  caen_code: 'CAEN',
  contact_person: 'Persoană de contact',
}

export function carrierLabel(carrier: string): string {
  return CARRIERS[carrier] ?? carrier
}

/** The label of a field key; `year` is the job year (the data year is year − 1). */
export function fieldLabel(key: string, fallback: string, year: number | null): string {
  if (key.endsWith('.unit')) return `${fieldLabel(key.slice(0, -5), fallback, year)} · unitate`
  const parts = key.split('.')
  if (parts[0] === 'carrier' && parts[1] && parts[2]) {
    const carrier = carrierLabel(parts[1])
    const month = parts[3] ? MONTHS[Number(parts[3]) - 1] : undefined
    return month ? `${carrier} · ${month} ${parts[2]}` : `${carrier} ${parts[2]}`
  }
  if (key === 'annual.total_tep') {
    return `Total ${year === null ? '' : String(year - 1)} vs Anexa „Date anuale”`
  }
  if (parts[0] === 'measure' && parts.length === 4 && parts[3]) {
    return `Măsura ${parts[2] ?? ''} · ${MEASURE_COLUMNS[parts[3]] ?? parts[3]}`
  }
  if (parts[0] === 'identity' && parts[1] && parts.length === 2) {
    return IDENTITY[parts[1]] ?? fallback
  }
  return fallback
}

const METHODS: Record<string, string> = {
  anexa: 'Anexa 2–3',
  questionnaire: 'Necesar info',
  prelucrare: 'Prelucrare',
  invoice: 'Factură',
}

export function docLabel(method: string): string {
  return METHODS[method] ?? method
}

export type ChipKind = 'document' | 'calculated' | 'manual' | 'online'

type EvidenceLike = {
  method: string
  provenance: string
  locator?: { kind: string; sheet?: string; ref?: string } | null
}

/** The source chip of an evidence record: kind and text. */
export function evidenceChip(evidence: EvidenceLike): { kind: ChipKind; text: string } {
  if (evidence.method === 'calc') return { kind: 'calculated', text: 'calculat' }
  if (evidence.method === 'manual') return { kind: 'manual', text: 'introdus manual' }
  if (evidence.provenance === 'online') return { kind: 'online', text: 'online' }
  return { kind: 'document', text: `${docLabel(evidence.method)} · ${cellReference(evidence)}` }
}

export function cellReference(evidence: EvidenceLike): string {
  const locator = evidence.locator
  if (!locator || locator.kind !== 'cell') return ''
  const ref = locator.ref ?? ''
  return ref.includes('!') ? ref : `${locator.sheet ?? ''}!${ref}`
}
