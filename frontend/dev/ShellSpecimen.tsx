import { Check, X } from 'lucide-react'
import { ActivityEntry, ActivityPanel } from '../src/ui/Activity'
import { Button, IconButton } from '../src/ui/Button'
import { Status } from '../src/ui/Chip'
import { EmaWidget, ProgressBar } from '../src/ui/Feedback'
import { Stepper, Tabs } from '../src/ui/Nav'
import {
  FieldReviewRow,
  Highlight,
  PageCrop,
  ReviewValue,
  Snippet,
  SourceButton,
} from '../src/ui/Review'
import {
  Content,
  NavClient,
  NavGroup,
  NavJob,
  NewJobButton,
  Sidebar,
  SidebarFooter,
  Window,
} from '../src/ui/Shell'
import { SectionKey } from '../src/ui/Surface'

// Synthetic data: the handoff's chrome copy with a made-up client.

/** Shell 3c: window, sidebar, content with stepper, widget and tabs, activity panel. */
export function ShellSpecimen() {
  return (
    <Window activity height={560}>
      <Sidebar
        action={<NewJobButton>Lucrare nouă</NewJobButton>}
        footer={<SidebarFooter initials="AP" name="Auditor" />}
      >
        <NavGroup title="În lucru">
          <NavClient color="olive">Client Exemplu 2026</NavClient>
          <NavJob active count={7}>
            Audit energetic 2023–25
          </NavJob>
          <NavJob working>Facturi 2025</NavJob>
          <NavJob>PIEE 2026</NavJob>
          <NavClient color="violet">Al doilea client</NavClient>
        </NavGroup>
        <NavGroup title="Finalizate">
          <NavJob finished>Audit Exemplu 2022</NavJob>
        </NavGroup>
      </Sidebar>
      <Content
        crumb="Client Exemplu 2026"
        title="Audit energetic 2023–2025"
        actions={
          <>
            <span className="ema-content__crumb">salvat acum 4 s</span>
            <Button variant="secondary" height={34}>
              Previzualizare
            </Button>
            <Button variant="olive" height={34} disabled>
              Exportă Word
            </Button>
          </>
        }
      >
        <div style={{ padding: '22px 0 18px' }}>
          <Stepper
            progress={70}
            steps={[
              { label: 'Configurare', detail: 'gata', state: 'done' },
              { label: 'Documente', detail: '12 / 14', state: 'done', tone: 'warn' },
              { label: 'Extragere', detail: '120 / 120', state: 'warn', tone: 'ok' },
              { label: 'Revizuire', detail: '7 în aşteptare', state: 'current', tone: 'warn' },
              { label: 'Raport Word', detail: '—', state: 'todo' },
            ]}
          />
        </div>
        <div style={{ display: 'flex', marginBottom: 16 }}>
          <EmaWidget
            title="Începe cu cele 3 câmpuri nesigure"
            actions={
              <>
                <Button height={32}>Du-mă la primul</Button>
                <Button variant="secondary" height={32}>
                  Acceptă cele 4 sigure
                </Button>
              </>
            }
          >
            Restul 4 au potrivire exactă în document — le poți accepta pe toate deodată.
          </EmaWidget>
        </div>
        <Tabs
          active="review"
          onSelect={() => undefined}
          items={[
            { id: 'docs', label: 'Documente', count: 14 },
            { id: 'structure', label: 'Structura raportului' },
            { id: 'review', label: 'Revizuire', count: 7, pending: true },
            { id: 'log', label: 'Jurnal' },
          ]}
          aside={
            <>
              <span style={{ color: 'var(--ink)', fontWeight: 500 }}>În aşteptare 7</span>
              <span>Nesigure 3</span>
              <span>Acceptate 113</span>
            </>
          }
        />
      </Content>
      <ActivityPanel
        title="Ce s-a întâmplat"
        footer={
          <>
            <div style={{ display: 'flex', alignItems: 'baseline' }}>
              <SectionKey>Cât a mai rămas</SectionKey>
              <span
                className="ema-type-mono"
                style={{ marginLeft: 'auto', color: 'var(--olive-ink)' }}
              >
                113 / 120
              </span>
            </div>
            <ProgressBar value={94} />
            <span className="ema-type-secondary" style={{ fontSize: 11.5 }}>
              Raportul se poate genera după ultimele 7.
            </span>
          </>
        }
      >
        <ActivityEntry
          outcome="accepted"
          title="Denumire operator"
          time="acum 9 s"
          detail="acceptat, scris la 2.1"
          undo="Anulează"
        />
        <ActivityEntry
          outcome="rejected"
          title="Randament cazan CT-2"
          time="acum 1 min"
          detail="92,4 % → 88,1 %, scris de tine"
          undo="Anulează"
        />
        <ActivityEntry outcome="info" title="Extragere încheiată · 120 câmpuri" time="acum 6 min" />
      </ActivityPanel>
    </Window>
  )
}

/** Review rows 3c: the open row with its paper snippet, then the closed outcomes. */
export function ReviewSpecimen() {
  return (
    <div className="sheet-fill">
      <FieldReviewRow
        label="Putere instalată totală"
        status={<Status tone="warn">potrivire parțială</Status>}
        value={<ReviewValue>4 218 kW</ReviewValue>}
        note="suma a 12 echipamente"
        source={<SourceButton open>Audit 2022 · pag. 14</SourceButton>}
        actions={
          <>
            <Button variant="olive" height={32} icon={Check}>
              Acceptă
            </Button>
            <IconButton icon={X} label="Respinge" />
          </>
        }
        snippet={
          <Snippet
            crop={
              <PageCrop
                label="Putere totală instalată"
                value="4.218 kW"
                page={14}
                reference="PAG. 14 / 48 · TABEL 3"
              />
            }
            quote={
              <>
                „Puterea electrică totală instalată la nivelul platformei este de{' '}
                <Highlight>4.218 kW</Highlight>, din care 3.960 kW în hala de producție și restul la
                utilități.”
              </>
            }
            reasonTitle="De ce e marcat nesigur"
            reason={
              <>
                Valoarea din document e din 2022. Suma fişelor tehnice de acum dă{' '}
                <strong>4 380 kW</strong> — diferenţă de 162 kW, probabil compresorul nou.
              </>
            }
            exits={
              <>
                <Button variant="secondary" height={30}>
                  Foloseşte 4 380 kW
                </Button>
                <Button variant="secondary" height={30}>
                  Scrie altă valoare
                </Button>
              </>
            }
          />
        }
      />
      <FieldReviewRow
        label="Denumire operator"
        status={
          <Status tone="ok" mark="accepted">
            acceptat acum 9 s
          </Status>
        }
        value={<ReviewValue>Client Exemplu S.A.</ReviewValue>}
        source={<SourceButton>Licenţă ANRE · pag. 1</SourceButton>}
        actions={
          <Button variant="soft" height={32}>
            Anulează
          </Button>
        }
      />
      <FieldReviewRow
        label="Consum anual 2024"
        status={
          <Status tone="muted" mark="working">
            se scrie în raport…
          </Status>
        }
        value={<ReviewValue>1 284 610 kWh</ReviewValue>}
        note="tabel 4.2 şi grafic 4.1"
        source={<SourceButton cell>Consumuri.xlsx · F2!C14</SourceButton>}
      />
      <FieldReviewRow
        label="Randament cazan CT-2"
        status={
          <Status tone="err" mark="rejected">
            respins acum 1 min
          </Status>
        }
        value={<ReviewValue previous="92,4 %">88,1 %</ReviewValue>}
        note="scris de tine · măsurare 03.2026"
        source={<SourceButton>Fişă cazane · pag. 3</SourceButton>}
        actions={
          <Button variant="soft" height={32}>
            Anulează
          </Button>
        }
      />
      <FieldReviewRow
        label="Ore de funcţionare / an"
        status={<Status tone="warn">două valori diferite</Status>}
        value={<ReviewValue>6 240 h</ReviewValue>}
        note="Audit 2022 spune 5 880 h"
        source={<SourceButton>2 surse</SourceButton>}
        actions={
          <>
            <Button variant="secondary" height={32} icon={Check}>
              Acceptă
            </Button>
            <IconButton icon={X} label="Respinge" />
          </>
        }
      />
    </div>
  )
}
