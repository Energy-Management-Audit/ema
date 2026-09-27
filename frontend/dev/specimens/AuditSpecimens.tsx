import { Button } from '../../src/ui/Button'
import { SourceChip, Status } from '../../src/ui/Chip'
import { FieldReviewRow, ReviewValue, SourceButton } from '../../src/ui/Review'
import { Paper, SectionKey } from '../../src/ui/Surface'
import { SheetFrame, SheetRow, type Theme } from '../SheetParts'
import '../../src/screens/audit/audit.css'

export function Specimens({ theme }: { theme: Theme }) {
  return (
    <SheetFrame id={`audit-${theme}`} theme={theme}>
      <div
        className="sheet-row__body"
        data-capture="audit"
        style={{ flexDirection: 'column', alignItems: 'stretch', gap: 26 }}
      >
        <SheetRow label="ChapterRow · closed/open" refs="3j">
          <div className="audit-structure" style={{ flex: 1 }}>
            <div className="audit-chapter">
              <div className="audit-chapter__row">
                <div>
                  <strong>2. Date de identificare</strong>
                  <Status tone="ok">gata</Status>
                </div>
                <p>Toate valorile au sursă în documente.</p>
                <Button variant="secondary" height={30}>
                  Deschide
                </Button>
              </div>
            </div>
            <div className="audit-chapter" data-open="true">
              <div className="audit-chapter__row">
                <div>
                  <strong>3. Proces tehnologic</strong>
                  <Status tone="warn">aşteaptă vizita în teren</Status>
                </div>
                <p>Descrierea fluxului tehnologic aşteaptă vizita în teren.</p>
                <Button variant="secondary" height={30}>
                  Închide
                </Button>
              </div>
              <div className="audit-chapter__open">
                <div className="audit-chapter__detail">
                  <div>
                    <SectionKey>SUBCAPITOLE</SectionKey>
                    <p>3.1 Fluxul tehnologic</p>
                  </div>
                  <div>
                    <SectionKey>CE ŢINE CAPITOLUL PE LOC</SectionKey>
                    <p>Vizita în teren.</p>
                    <SectionKey>NOTIŢA TA</SectionKey>
                    <Paper>Verifică schema instalaţiei.</Paper>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </SheetRow>
        <SheetRow label="Section states" refs="M8">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, flex: 1 }}>
            <div className="audit-section-row">
              <div>
                <Status tone="ok">ciornă gata</Status>
                <span>3.3 Iluminat</span>
              </div>
            </div>
            <div className="audit-section-row">
              <div>
                <Status tone="warn">nu se aplică · propus</Status>
                <span>4.2.6 Energie termică terţi</span>
              </div>
              <Button height={28}>Confirmă „nu se aplică”</Button>
            </div>
            <div className="audit-section-row">
              <div>
                <Status tone="warn">mai târziu · vizită</Status>
                <span>5.2 Bilanţ termic</span>
              </div>
            </div>
          </div>
        </SheetRow>
        <SheetRow label="EvidencePanel · online/calculated" refs="M5">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, flex: 1 }}>
            <FieldReviewRow
              label="Factor de emisie"
              status={<Status tone="warn">din online · de confirmat</Status>}
              value={<ReviewValue>0,233 tCO₂/MWh</ReviewValue>}
              source={<SourceButton open>example.org · 27.09.2026</SourceButton>}
              snippet={
                <Paper>
                  <SectionKey>PAGINĂ WEB · instantaneu salvat</SectionKey>
                  <p>Factorul şi pagina sursă.</p>
                  <SectionKey>CITATUL DIN PAGINĂ</SectionKey>
                  <p>Valoarea găsită în pagina salvată.</p>
                </Paper>
              }
            />
            <FieldReviewRow
              label="Economie calculată"
              status={<Status tone="warn">calculat · se actualizează singur</Status>}
              value={<ReviewValue>840 MWh/an</ReviewValue>}
              source={<SourceChip kind="calculated">calculat · 2 intrări</SourceChip>}
              snippet={
                <Paper>
                  <SectionKey>Vezi intrările</SectionKey>
                  <p>Consum de referinţă · economie propusă</p>
                </Paper>
              }
            />
          </div>
        </SheetRow>
      </div>
    </SheetFrame>
  )
}
