import type { InvoiceRow as InvoiceDataRow } from '../../src/api/invoices-types.ts'
import { InvoiceRow, MonthBars } from '../../src/screens/invoices/InvoiceTable.tsx'
import { SheetFrame, SheetRow, type Theme } from '../SheetParts.tsx'
import '../../src/screens/invoices/invoices.css'

const base = {
  id: 'specimen',
  month: '2026-10',
  consumption_kwh: '142118',
  source_evidence_ids: [],
  anomalies: [],
  file_name: 'factura.pdf',
  slot: 'invoices/0001',
  supplier: 'Furnizor Exemplu',
  invoice_number: 'F-101',
  invoice_date: '2026-10-31',
  status: 'exportable',
  issues: [],
  price_lei_kwh: '2.200',
  value_lei: '312660',
  sources: { active_energy: { page: 1, snippet: 'Consum: 142.118 kWh' } },
  outlier: null,
} satisfies InvoiceDataRow

export function Specimens({ theme }: { theme: Theme }) {
  return (
    <SheetFrame id={`invoices-${theme}`} theme={theme}>
      <div
        data-capture="invoices"
        className="sheet-row__body"
        style={{ flexDirection: 'column', alignItems: 'stretch', gap: 26 }}
      >
        <SheetRow label="MonthBars · gap and outlier" refs="3f">
          <MonthBars
            year={2026}
            rows={[
              base,
              { ...base, id: 'gap-neighbour', month: '2026-09', consumption_kwh: '100000' },
              {
                ...base,
                id: 'outlier',
                month: '2026-11',
                outlier: { ratio: '1.4', neighbours_mean_kwh: '100000' },
              },
            ]}
          />
        </SheetRow>
        <SheetRow label="InvoiceRow · normal, outlier, requires review" refs="3f">
          <div className="invoice-table__rows" style={{ width: '100%' }}>
            <InvoiceRow jobId="specimen" row={base} open={false} onToggle={() => {}} />
            <InvoiceRow
              jobId="specimen"
              row={{
                ...base,
                id: 'outlier',
                outlier: { ratio: '1.34', neighbours_mean_kwh: '100000' },
              }}
              open={false}
              onToggle={() => {}}
            />
            <InvoiceRow
              jobId="specimen"
              row={{
                ...base,
                id: 'review',
                status: 'requires_review',
                issues: ['Preţul nu a fost găsit.'],
              }}
              open={false}
              onToggle={() => {}}
            />
          </div>
        </SheetRow>
      </div>
    </SheetFrame>
  )
}
