// The synthetic job's fields and evidence (invented company and figures; no client data).

export const JOB = 'job-piee-1'
const at = '2026-09-25T08:00:00+00:00'

const evidence = {}
function cell(id, method, sheet, ref, sha = `sha-${method}`) {
  evidence[id] = {
    id,
    provenance: 'document',
    file_sha: sha,
    locator: { kind: 'cell', sheet, ref: `${sheet}!${ref}` },
    method,
    retrieved_at: at,
    highlight: 'exact',
  }
  return id
}
function calc(id, inputs) {
  evidence[id] = {
    id,
    provenance: 'calculated',
    locator: { kind: 'cell', sheet: 'derived', ref: 'annual.total_tep' },
    method: 'calc',
    retrieved_at: at,
    highlight: 'none',
    derivation: { formula_id: 'tep.total', inputs, factor_version: 'FACTORS-2026' },
  }
  return id
}

function field(id, key, value, extra = {}) {
  const numeric = typeof value === 'string' && /^-?\d+(\.\d+)?$/.test(value) && !extra.value_type
  return {
    id,
    job_id: JOB,
    chapter: '',
    key,
    label: key,
    value_type: numeric ? 'number' : 'text',
    unit: null,
    required: false,
    value,
    revision: 1,
    state: 'extracted',
    presence: value === null ? 'not_found' : 'found',
    review: 'pending',
    confidence: value === null ? 'none' : 'exact',
    evidence: [],
    derivation: null,
    alternatives: [],
    chosen: null,
    failure: null,
    ...extra,
  }
}

const monthly = {
  electricity_grid: {
    2023: [
      '2811.40',
      '2540.22',
      '2602.13',
      '2330.57',
      '2400.10',
      '2380.00',
      '2455.60',
      '2470.25',
      '2390.80',
      '2512.34',
      '2680.11',
      '2745.90',
    ],
    2024: [
      '2790.11',
      '2612.48',
      '2588.90',
      '2401.33',
      '2395.00',
      '2366.70',
      '2444.12',
      '2481.02',
      '2402.90',
      '2530.64',
      '2690.33',
      '2702.15',
    ],
    2025: [
      '2698.20',
      '2480.64',
      '2511.08',
      '2356.71',
      '2350.00',
      '2320.44',
      '2400.00',
      '2455.25',
      '2380.10',
      '2500.12',
      '2620.33',
      '2660.02',
    ],
  },
  natural_gas: {
    2023: [
      '9100.5',
      '8800',
      '7600.25',
      '5400',
      '3100',
      '2400',
      '2300',
      '2350',
      '3050',
      '5200',
      '7400',
      '8900',
    ],
    2024: [
      '9050',
      '8700',
      '7500',
      '5300',
      '3000',
      '2300',
      '2250',
      '2300',
      '3000',
      '5100',
      '7300',
      '8800',
    ],
    2025: [
      '8950',
      '8600',
      '7450',
      '5250',
      '2950',
      '2280',
      '2200',
      '2290',
      '2980',
      '5050',
      '7250',
      '8700',
    ],
  },
}
const annual = {
  electricity_grid: { 2023: '30319.36', 2024: '30405.48', 2025: '29732.89' },
  natural_gas: { 2023: '65600.75', 2024: '64600', 2025: '63950' },
}

const fields = []
for (const [carrier, years] of Object.entries(monthly)) {
  for (const [year, values] of Object.entries(years)) {
    const source = Number(year) === 2025 ? 'questionnaire' : 'prelucrare'
    const sheet = source === 'questionnaire' ? 'Cons energetice' : 'Consum Electric'
    const annualId = `f-${carrier}-${year}`
    fields.push(
      field(annualId, `carrier.${carrier}.${year}`, annual[carrier][year], {
        unit: 'MWh',
        evidence: [cell(`e-${carrier}-${year}`, source, sheet, `D${String(Number(year) - 2012)}`)],
      }),
    )
    values.forEach((value, index) => {
      const month = String(index + 1).padStart(2, '0')
      fields.push(
        field(`f-${carrier}-${year}-${month}`, `carrier.${carrier}.${year}.${month}`, value, {
          unit: 'MWh',
          evidence: [cell(`e-${carrier}-${year}-${month}`, source, sheet, `E${String(index + 5)}`)],
        }),
      )
    })
  }
}
fields.push(
  field('f-pv-2025', 'carrier.electricity_pv.2025', '61.32', {
    unit: 'MWh',
    evidence: [cell('e-pv-2025', 'questionnaire', 'Cons energetice', 'N23')],
  }),
)

export const ANNUAL = field('f-annual', 'annual.total_tep', '22164.05', {
  label: 'Date anuale total tep',
  unit: 'tep',
  required: true,
  confidence: 'conflict',
  revision: 3,
  evidence: ['e-calc'],
  alternatives: [
    {
      id: 'c-calc',
      value: '22164.05',
      evidence: [
        calc('e-calc', [
          'carrier.electricity_grid.2025',
          'carrier.natural_gas.2025',
          'carrier.electricity_pv.2025',
        ]),
      ],
    },
    {
      id: 'c-anexa',
      value: '22161.92',
      evidence: [cell('e-anexa-total', 'anexa', 'Date anuale', 'F21', 'sha-anexa')],
    },
  ],
})
fields.push(ANNUAL)
fields.push(
  field('f-name', 'identity.name', 'Exemplu Energie SA', {
    label: 'name',
    required: true,
    evidence: [cell('e-name', 'anexa', 'Date generale', 'C5', 'sha-anexa')],
  }),
  field('f-cui', 'identity.cui', 'RO1234567', {
    label: 'cui',
    evidence: [cell('e-cui', 'anexa', 'Date generale', 'C6', 'sha-anexa')],
  }),
)
export const REGISTRU = field('f-registru', 'identity.registrul_comertului', null, {
  label: 'Registrul Comerţului',
})
fields.push(REGISTRU)

const measures = [
  ['planned', 1, 'Izolare conducte abur', '184', '238', '1.8', 2026],
  ['planned', 2, 'Variaţie turaţie pompe reţea', '96', '104', '3.1', null],
  ['planned', 3, 'Compensarea factorului de putere', '132', '86', '4.2', 2027],
  ['planned', 4, 'Economizor gaze arse CT-2', '248', '412', '2.43', 2026],
  ['existing', 1, 'Iluminat LED hală', '40', '52', '1.6', 2024],
  ['existing', 2, 'Recuperare căldură compresoare', '75', '90', '2.2', 2025],
  ['audit', 1, 'Program de mentenanţă arzătoare', null, '148', null, 2026],
]
const sheets = {
  planned: 'Solutii EE planificate',
  existing: 'Solutii EE',
  audit: 'Audit energetic',
}
for (const [group, index, description, investment, saving, payback, term] of measures) {
  const base = `measure.${group}.${String(index)}`
  const tag = `${group}-${String(index)}`
  const sheet = sheets[group]
  const row = String(10 + index)
  fields.push(
    field(`f-${tag}-description`, `${base}.description`, description, {
      evidence: [cell(`e-${tag}-description`, 'anexa', sheet, `B${row}`, 'sha-anexa')],
    }),
    field(`f-${tag}-investment`, `${base}.investment_thousand_lei`, investment, {
      value_type: 'number',
      unit: 'mii lei',
      evidence:
        investment === null
          ? []
          : [cell(`e-${tag}-investment`, 'anexa', sheet, `D${row}`, 'sha-anexa')],
    }),
    field(`f-${tag}-saving`, `${base}.saving_mwh`, saving, {
      value_type: 'number',
      unit: 'MWh',
      evidence: [cell(`e-${tag}-saving`, 'anexa', sheet, `E${row}`, 'sha-anexa')],
    }),
    field(`f-${tag}-payback`, `${base}.payback_years`, payback, {
      value_type: 'number',
      unit: 'ani',
      state: payback === null ? 'extracted' : 'calculated',
      evidence: [],
    }),
  )
  if (term !== null) {
    fields.push(
      field(`f-${tag}-term`, `${base}.commissioning_year`, term, {
        value_type: 'number',
        evidence: [cell(`e-${tag}-term`, 'anexa', sheet, `F${row}`, 'sha-anexa')],
      }),
    )
  }
}
export const TERM_P2 = field('f-term-p2', 'measure.planned.2.commissioning_year', null, {
  value_type: 'year',
})
fields.push(TERM_P2)
export const FIELDS = fields.sort((a, b) => a.key.localeCompare(b.key))
export const EVIDENCE = evidence
