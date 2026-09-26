import { SourceChip } from '../src/ui/Chip'
import { Button } from '../src/ui/Button'
import { AnnualCheckLine, CountBar, KpiTile } from '../src/ui/Figures'
import { DocThumb, ExportCheck, PackageFile } from '../src/ui/Package'
import { SheetFrame, SheetRow, type Theme } from './SheetParts'

/** The six components S17b adds for the PIEE screens, each with its design id. */
export function PieeSpecimens({ theme }: { theme: Theme }) {
  return (
    <SheetFrame id={`piee-${theme}`} theme={theme}>
      <div
        className="sheet-row__body"
        data-capture="piee"
        style={{ flexDirection: 'column', alignItems: 'stretch', gap: 26 }}
      >
        <SheetRow label="KpiTile · CountBar · AnnualCheckLine" refs="3g · OVERRIDES §1">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18, flex: 1 }}>
            <div style={{ display: 'flex', gap: 34 }}>
              <CountBar label="Măsuri gata de export" done={5} total={7} />
              <CountBar label="Măsuri gata de export" done={7} total={7} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 26 }}>
              <KpiTile label="ECONOMIE ANGAJATĂ" value="840" unit="MWh/an" />
              <KpiTile label="INVESTIŢIE" value="660" unit="mii lei" note="fără 1 măsuri" />
              <KpiTile
                label="TOTAL ENERGIE"
                value="22 164,05"
                unit="tep"
                source={<SourceChip kind="calculated">calculat</SourceChip>}
              />
              <AnnualCheckLine
                state="mismatch"
                action={
                  <Button height={28} variant="primary">
                    Du-mă la conflict
                  </Button>
                }
              >
                Totalul anual nu se potriveşte cu Anexa 2–3
              </AnnualCheckLine>
            </div>
            <AnnualCheckLine state="match">
              Totalul anual se potriveşte cu Anexa 2–3 · „Date anuale”
            </AnnualCheckLine>
          </div>
        </SheetRow>
        <SheetRow label="DocThumb · ExportCheck · PackageFile" refs="7a">
          <div style={{ display: 'flex', gap: 26, flex: 1 }}>
            <DocThumb title="PIEE 2026" lines="7 MĂSURI" meta="generat acum 3 min" />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18, flex: 1 }}>
              <div>
                <ExportCheck
                  tone="ok"
                  label="Toate diferenţele dintre surse sunt decise"
                  detail="0 deschise"
                />
                <ExportCheck
                  tone="warn"
                  label="Toate cele 7 măsuri au termen, investiţie, economie şi recuperare"
                  detail="5 / 7"
                />
                <ExportCheck
                  tone="err"
                  label="Totalul anual coincide cu „Date anuale” din Anexa 2–3"
                  detail="22 164,05 tep"
                />
              </div>
              <div
                className="export__files"
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  border: '1px solid var(--border)',
                  borderRadius: 14,
                  overflow: 'hidden',
                }}
              >
                <PackageFile name="PIEE-final.docx" size="4,1 MB" kind="docx" />
                <PackageFile name="PIEE-final.pdf" size="1,8 MB" kind="pdf" />
                <PackageFile name="Prelucrare-date.xlsx" size="96 KB" kind="xlsx" />
              </div>
            </div>
          </div>
        </SheetRow>
      </div>
    </SheetFrame>
  )
}
