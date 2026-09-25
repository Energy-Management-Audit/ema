import { Button } from '../src/ui/Button'
import { EmptyState, FailureNotice, ItemLine, ProgressBar } from '../src/ui/Feedback'
import { Card, CardHeader } from '../src/ui/Surface'

/** The four shell states of 7b: empty, extracting, upload failed, nothing left to review. */
export function StateSpecimens() {
  return (
    <div
      data-capture="states"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
        gap: 34,
        flex: 1,
      }}
    >
      <Card height={400}>
        <EmptyState
          mark="brand"
          title="Începe cu un audit"
          footnote="PDF · DOCX · XLSX · max. 200 MB"
          actions={
            <>
              <Button>Alege fişiere</Button>
              <Button variant="secondary">Vezi un exemplu</Button>
            </>
          }
        >
          Trage aici auditul energetic în PDF sau Word. Ema îl citeşte, extrage datele şi pregăteşte
          raportul. Facturile şi PIEE vin după.
        </EmptyState>
      </Card>

      <Card height={400}>
        <CardHeader title="Audit energetic 2023–2025" count="61 pagini" aside="~2 min rămase" />
        <div
          style={{
            display: 'flex',
            flex: 1,
            flexDirection: 'column',
            justifyContent: 'center',
            gap: 22,
            padding: '0 34px',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', fontSize: 13 }}>
              <span>Citesc capitolul 6 — măsuri propuse</span>
              <span className="ema-mono" style={{ marginLeft: 'auto', fontSize: 12 }}>
                84 / 120
              </span>
            </div>
            <ProgressBar value={70} running />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <ItemLine dense state="done" detail="18 câmpuri">
              Date de identificare
            </ItemLine>
            <ItemLine dense state="done" detail="54 câmpuri">
              Consumuri şi bilanţ
            </ItemLine>
            <ItemLine dense state="working" detail="12 din 18">
              Măsuri propuse
            </ItemLine>
          </div>
          <span className="ema-type-secondary" style={{ fontSize: 12 }}>
            Poţi pleca din ecran — te anunţ când termin. Ce e deja extras se poate revizui acum.
          </span>
        </div>
      </Card>

      <Card height={400}>
        <CardHeader title="Documente" count="12 din 14" />
        <div style={{ display: 'flex', flex: 1, flexDirection: 'column', padding: '18px 20px' }}>
          <FailureNotice
            title="factura_decembrie.pdf nu a putut fi citită"
            actions={
              <>
                <Button height={30}>Reîncarcă</Button>
                <Button variant="secondary" height={30}>
                  Introdu manual
                </Button>
              </>
            }
          >
            Fişierul e o scanare fără text şi la 110 dpi. Sub 200 dpi nu pot extrage cifrele cu
            încredere.
          </FailureNotice>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 6 }}>
            <ItemLine state="done" detail="extras">
              factura_octombrie.pdf
            </ItemLine>
            <ItemLine state="done" detail="extras">
              factura_noiembrie.pdf
            </ItemLine>
            <ItemLine state="failed" detail="eşuat">
              factura_decembrie.pdf
            </ItemLine>
          </div>
          <span
            className="ema-type-mono"
            style={{ marginTop: 'auto', fontFamily: 'var(--font-sans)', fontSize: 12 }}
          >
            Celelalte 11 facturi au fost procesate. Eroarea nu opreşte lucrarea.
          </span>
        </div>
      </Card>

      <Card height={400}>
        <CardHeader title="Revizuire" count="0 în aşteptare" />
        <EmptyState
          mark="done"
          title="Toate cele 120 de câmpuri sunt acceptate"
          actions={
            <>
              <Button height={36}>Treci la structură</Button>
              <Button variant="secondary" height={36}>
                Vezi cele 120 acceptate
              </Button>
            </>
          }
        >
          Nu mai e nimic de confirmat. Următorul pas e structura raportului.
        </EmptyState>
      </Card>
    </div>
  )
}
