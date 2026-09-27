import type { RenderSummary } from '../../src/api/audit-report-types.ts'
import { tocItems } from '../../src/audit/report.ts'
import { ReportPanel } from '../../src/screens/audit/ReportPanel.tsx'
import { ReportToc } from '../../src/screens/audit/ReportToc.tsx'
import '../../src/screens/audit/report.css'
import { SheetFrame, SheetRow, type Theme } from '../SheetParts'

const SUMMARY: RenderSummary = {
  kind: 'draft',
  chapters: [
    { number: 1, title: 'Descrierea şi scopul auditului', section_id: 'ch1', page: 4 },
    { number: 2, title: 'Descrierea şi istoricul societăţii', section_id: 'ch2', page: 9 },
    { number: 3, title: 'Descrierea situaţiei existente', section_id: 'ch3', page: 14 },
    { number: 4, title: 'Analiza consumurilor energetice', section_id: 'ch4', page: 31 },
    { number: 5, title: 'Măsuri de creştere a eficienţei energetice', section_id: 'ch6', page: 52 },
    { number: 6, title: 'Surse de finanţare', section_id: 'ch7', page: 61 },
  ],
  tables: 9,
  charts: 4,
  markers: [
    { section_id: 'ch4.concluzii', label: 'Concluziile analizei' },
    { section_id: 'ch3.flux', label: 'Descrierea fluxului tehnologic' },
  ],
  fields_total: 120,
  fields_confirmed: 120,
  fields_manual: 0,
  unit_plan: {
    client_name: 'Exemplu Energie SA',
    processes: 2,
    processes_source: 'default',
    carriers: ['electricity', 'gas'],
    measured_panels: 4,
    thermal_measurements: true,
    equipment_tables: 1,
    measures: 3,
  },
  pdf: true,
  toc_pages_set: true,
  dropped: [],
  failures: [{ section_id: 'ch6', code: 'draft_slots' }],
}

const FILE = { name: 'Audit-ciorna.docx', size: '2,3 MB' }

/** The Raport Word (3d) parts: the report panel with and without markers, CUPRINS states. */
export function Specimens({ theme }: { theme: Theme }) {
  return (
    <SheetFrame id={`report-${theme}`} theme={theme}>
      <div
        className="sheet-row__body"
        data-capture="report"
        style={{ flexDirection: 'column', alignItems: 'stretch', gap: 26 }}
      >
        <SheetRow label="ReportPanel · with markers · without" refs="3d">
          <div style={{ display: 'flex', gap: 26, height: 560 }}>
            <div style={{ display: 'grid', width: 290 }}>
              <ReportPanel summary={SUMMARY} file={FILE} onFill={() => undefined} />
            </div>
            <div style={{ display: 'grid', width: 290 }}>
              <ReportPanel
                summary={{ ...SUMMARY, markers: [], failures: [], fields_confirmed: 118 }}
                file={FILE}
              />
            </div>
          </div>
        </SheetRow>
        <SheetRow label="ReportToc · before a render · writing · done" refs="3d">
          <div style={{ display: 'flex', gap: 26 }}>
            {[
              tocItems(null, { running: false, done: 0, total: 0 }),
              tocItems(SUMMARY, { running: true, done: 3, total: 6 }),
              tocItems(SUMMARY, { running: false, done: 0, total: 0 }),
            ].map((items, index) => (
              <div key={index} style={{ width: 220 }}>
                <ReportToc items={items} markers={index === 2 ? 2 : 0} onJump={() => undefined} />
              </div>
            ))}
          </div>
        </SheetRow>
      </div>
    </SheetFrame>
  )
}
