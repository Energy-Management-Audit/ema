import { ContactCard } from '../../src/screens/clients/ClientCards'
import { ExceptionsBox } from '../../src/screens/reporting/ReportingParts'
import { SheetFrame, SheetRow, type Theme } from '../SheetParts'

export function Specimens({ theme }: { theme: Theme }) {
  const exceptions = [
    ['EROARE', 'Verifică anul din anexă.'],
    ['REVIZUIRE', 'Costul lipseşte.'],
    ['INFORMARE', 'Măsura nu are economie.'],
  ].map(([code, detail]) => ({
    client_id: 'synthetic-client',
    year: 2026,
    code,
    detail,
    source_name: 'Anexa-Exemplu.xlsx',
    beneficiary: 'Exemplu Energie SA',
    decision: null,
    ref: 'Anexa 2–3 · D12',
  }))
  return (
    <SheetFrame id={`clients-${theme}`} theme={theme}>
      <div
        className="sheet-row__body"
        data-capture="clients"
        style={{ flexDirection: 'column', alignItems: 'stretch', gap: 26 }}
      >
        <SheetRow label="ContactCard · complete and missing" refs="M2">
          <div style={{ display: 'flex', gap: 20, flex: 1 }}>
            <ContactCard
              title="DATE PRIVIND MANAGERUL ENERGETIC"
              name="Manager Exemplu"
              missing="Nu e completat."
              onComplete={() => {}}
            />
            <ContactCard
              title="PERSOANĂ DE CONTACT"
              name={null}
              missing="Nu apare în Anexa 2–3 2026."
              onComplete={() => {}}
            />
          </div>
        </SheetRow>
        <SheetRow label="ExceptionsBox · all severities" refs="M3">
          <ExceptionsBox exceptions={exceptions} clients={[]} />
        </SheetRow>
      </div>
    </SheetFrame>
  )
}
