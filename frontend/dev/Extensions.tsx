import { useState } from 'react'
import { Download, File, FileText, Folder, Info, Shield, Sun, X } from 'lucide-react'
import { Button, IconButton } from '../src/ui/Button'
import { SourceChip, Spinner, Status, Tag } from '../src/ui/Chip'
import { CheckRow, Dialog } from '../src/ui/Dialog'
import { ProgressBar } from '../src/ui/Feedback'
import { KeyInput, Toggle } from '../src/ui/Field'
import { NavItem } from '../src/ui/Shell'
import { GroupBox, GroupRow } from '../src/ui/Surface'
import { SheetFrame, SheetRow, type Theme } from './SheetParts'
import { ReviewSpecimen, ShellSpecimen } from './ShellSpecimen'
import { StateSpecimens } from './StateSpecimens'

function Provisional({ children }: { children: string }) {
  return <span className="sheet-provisional">{children}</span>
}

function SettingsSpecimen() {
  const [ocr, setOcr] = useState(true)
  const [uncertain, setUncertain] = useState(true)
  const [autoAccept, setAutoAccept] = useState(false)
  return (
    <div style={{ display: 'flex', gap: 34, flex: 1, alignItems: 'flex-start' }}>
      <nav
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
          width: 230,
          padding: 14,
          borderRadius: 16,
          background: 'var(--surface-sunken)',
        }}
      >
        <NavItem icon={File} active>
          Extragere
        </NavItem>
        <NavItem icon={FileText}>Rapoarte</NavItem>
        <NavItem icon={Download}>Şabloane</NavItem>
        <NavItem icon={Folder}>Fişiere şi dosare</NavItem>
        <NavItem icon={Shield}>Confidenţialitate</NavItem>
        <NavItem icon={Sun}>Aspect</NavItem>
        <NavItem icon={Info}>Despre Ema</NavItem>
      </nav>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 26, flex: 1, maxWidth: 720 }}>
        <GroupBox>
          <GroupRow
            title="Gemini"
            tag={<Tag>IMPLICIT</Tag>}
            description="Modelul care citeşte documentele şi propune valorile. Dacă ai chei pentru amândouă, Ema o foloseşte pe cea marcată implicit."
            state={<Status tone="ok">cheie adăugată · verificată acum 2 h</Status>}
            control={
              <>
                <span className="ema-type-mono" style={{ fontSize: 12, color: 'var(--ink-muted)' }}>
                  AIza••••••••7Kd2
                </span>
                <Button variant="secondary" height={30}>
                  Înlocuieşte
                </Button>
                <IconButton icon={X} label="Şterge cheia" size={30} bordered={false} />
              </>
            }
          />
          <GroupRow
            title="OpenAI"
            description="Alternativă la Gemini. Nu e nevoie de amândouă."
            state={
              <Status tone="muted" mark="none">
                fără cheie
              </Status>
            }
            control={
              <>
                <KeyInput placeholder="sk-…" aria-label="Cheie OpenAI" />
                <Button height={30}>Adaugă</Button>
              </>
            }
          />
        </GroupBox>
        <GroupBox>
          <GroupRow
            title="OCR pentru documente scanate"
            description="Porneşte singur când un PDF nu are text. Adaugă circa 40 s per document."
            control={
              <Toggle checked={ocr} onChange={setOcr} label="OCR pentru documente scanate" />
            }
          />
          <GroupRow
            title="Marchează valorile nesigure"
            description="Când o valoare apare diferit în două documente, Ema o trece la revizuire în loc să aleagă singură."
            control={
              <Toggle
                checked={uncertain}
                onChange={setUncertain}
                label="Marchează valorile nesigure"
              />
            }
          />
          <GroupRow
            title="Acceptă automat potrivirile exacte"
            description="Rămân în jurnal şi pot fi anulate oricând."
            control={
              <Toggle
                checked={autoAccept}
                onChange={setAutoAccept}
                label="Acceptă automat potrivirile exacte"
              />
            }
          />
        </GroupBox>
      </div>
    </div>
  )
}

function DialogSpecimens() {
  const [keep, setKeep] = useState(false)
  const [open, setOpen] = useState(false)
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 30,
        padding: 34,
        borderRadius: 20,
        background: 'rgb(var(--ink-rgb) / 0.06)',
      }}
    >
      <Button
        data-dialog-open
        onClick={() => {
          setOpen(true)
        }}
      >
        Deschide dialogul 7c
      </Button>
      {open && (
        <Dialog
          title="Ştergi „Facturi 2025”?"
          content={
            <CheckRow checked={keep} onChange={setKeep}>
              Păstrează fişierele originale în arhivă
            </CheckRow>
          }
          actions={
            <>
              <Button
                variant="secondary"
                height={36}
                onClick={() => {
                  setOpen(false)
                }}
              >
                Renunţă
              </Button>
              <Button
                variant="destructive"
                height={36}
                onClick={() => {
                  setOpen(false)
                }}
              >
                Şterge modulul
              </Button>
            </>
          }
          onClose={() => {
            setOpen(false)
          }}
        >
          Se şterg 11 facturi încărcate şi 54 de câmpuri extrase din ele. Auditul şi PIEE-ul din
          aceeaşi lucrare rămân neatinse. Acţiunea nu poate fi anulată.
        </Dialog>
      )}
    </div>
  )
}

/** Components the screens use beyond 7d/7e, each labelled with the design id it reproduces. */
export function Extensions({ theme }: { theme: Theme }) {
  return (
    <SheetFrame id={`extensions-${theme}`} theme={theme}>
      <SheetRow wide label="FEREASTRĂ" refs="3c">
        <div className="sheet-fill" data-capture="shell">
          <ShellSpecimen />
        </div>
      </SheetRow>
      <SheetRow label="REVIZUIRE" refs="3c">
        <div className="sheet-fill" data-capture="review">
          <ReviewSpecimen />
        </div>
      </SheetRow>
      <SheetRow label="SETĂRI" refs="3i">
        <div className="sheet-fill" data-capture="settings">
          <SettingsSpecimen />
        </div>
      </SheetRow>
      <SheetRow label="SURSE" refs="M5">
        <div className="sheet-row__body" data-capture="sources">
          <SourceChip kind="document">Audit 2022 · pag. 14</SourceChip>
          <SourceChip kind="document">Necesar info · B22</SourceChip>
          <SourceChip kind="online">insse.ro · 22.09.2026</SourceChip>
          <SourceChip kind="calculated">calculat · 6 intrări</SourceChip>
          <SourceChip kind="manual">
            <Provisional>introdus manual</Provisional>
          </SourceChip>
        </div>
      </SheetRow>
      <SheetRow label="STARE" refs="7d · 3j · M8">
        <div className="sheet-row__body" data-capture="statuses" style={{ columnGap: 22 }}>
          <Status tone="ok">ciornă gata</Status>
          <Status tone="ok" mark="accepted">
            acceptat acum 9 s
          </Status>
          <Status tone="warn">aşteaptă vizita în teren</Status>
          <Status tone="warn" mark="later">
            mai târziu · vizită
          </Status>
          <Status tone="muted" mark="na">
            <Provisional>nu se aplică · propus</Provisional>
          </Status>
          <Status tone="err">eşuat</Status>
          <Status tone="err" mark="rejected">
            respins acum 1 min
          </Status>
          <Status tone="muted" mark="working">
            se scrie în raport…
          </Status>
          <Spinner />
          <span style={{ width: 160 }}>
            <ProgressBar value={70} />
          </span>
        </div>
      </SheetRow>
      <SheetRow wide label="STĂRI ECRAN" refs="7b">
        <StateSpecimens />
      </SheetRow>
      <SheetRow wide label="DIALOGURI" refs="7c">
        <div className="sheet-fill" data-capture="dialogs">
          <DialogSpecimens />
        </div>
      </SheetRow>
    </SheetFrame>
  )
}
