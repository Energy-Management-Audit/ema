import { File, X } from 'lucide-react'
import { Button, IconButton } from '../src/ui/Button'
import { MissingChip, PageChip, Status, StatusChip } from '../src/ui/Chip'
import { EmaWidget } from '../src/ui/Feedback'
import { MissingField, Select, TextField } from '../src/ui/Field'
import { Icon, type IconSize } from '../src/ui/Icon'
import { Cell, ListRow, TableRow } from '../src/ui/Rows'
import { Legend, SheetFrame, SheetRow, Swatch, TokenTable, type Theme } from './SheetParts'

const swatches: Record<Theme, [color: string, hex: string, name: string][]> = {
  light: [
    ['var(--surface)', '#f6f2e8', 'fundal'],
    ['var(--surface-sunken)', '#f0ebde', 'panou'],
    ['var(--ink)', '#252219', 'text'],
    ['var(--olive)', '#4f7015', 'oliv'],
    ['var(--amber)', '#b8751a', 'chihlimbar'],
    ['var(--error)', '#9e3f1f', 'eroare'],
    ['var(--violet)', '#7a5ea8', 'al doilea client'],
  ],
  dark: [
    ['var(--surface)', '#1e1b16', 'fundal'],
    ['var(--surface-sunken)', '#181510', 'panou'],
    ['var(--ink)', '#ece5d5', 'text'],
    ['var(--olive)', '#9bbb52', 'oliv'],
    ['var(--amber)', '#d8a24e', 'chihlimbar'],
    ['var(--error)', '#e8836a', 'eroare'],
    ['var(--violet)', '#a58cd4', 'al doilea client'],
  ],
}

const iconSizes: [IconSize, string][] = [
  [13, 'în etichete'],
  [14, 'în butoane mici'],
  [16, 'în navigaţie'],
  [17, 'în stări'],
  [20, 'titluri de panou'],
]

const buttonStates = ['normal', 'hover', 'activ', 'încărcare', 'dezactivat'] as const

/** 7d / 7e rebuilt row for row from the real components; the pixel side-by-side reference. */
export function ComponentSheet({ theme }: { theme: Theme }) {
  const inkRgba = theme === 'dark' ? 'rgba(236,229,213,.05)' : 'rgba(37,34,25,.05)'
  return (
    <SheetFrame id={theme === 'dark' ? 'sheet-7e' : 'sheet-7d'} theme={theme}>
      <SheetRow label="BUTOANE">
        <Button>Primar</Button>
        <Button variant="secondary">Secundar</Button>
        <Button variant="tertiary">Terţiar</Button>
        <Button variant="destructive">Distructiv</Button>
        <Button variant="secondary" disabled>
          Dezactivat
        </Button>
        <IconButton icon={X} label="Închide" />
        <Legend>h 38 · r 21 · h 30-32 în rânduri</Legend>
      </SheetRow>

      <SheetRow label="ETICHETE">
        <StatusChip tone="ok">confirmat</StatusChip>
        <StatusChip tone="warn">de verificat</StatusChip>
        <StatusChip tone="err">eşuat</StatusChip>
        <MissingChip>câmp lipsă</MissingChip>
        <PageChip>pag. 44</PageChip>
      </SheetRow>

      <SheetRow label="CULORI">
        {swatches[theme].map(([color, hex, name]) => (
          <Swatch key={name} color={color} hex={hex} name={name} />
        ))}
        <Swatch color="#1e1b16" hex="#1e1b16" name="fundal întunecat" ring={false} />
      </SheetRow>

      <SheetRow label="TIPOGRAFIE">
        <div className="sheet-fill" style={{ gap: 7 }}>
          <span className="ema-type-screen-title ema-type-screen-title--dense">
            Titlu ecran · Geist 30/500
          </span>
          <span className="ema-type-job-title">Titlu lucrare · 23/500</span>
          <span className="ema-type-row">Rând principal · 13,5/500</span>
          <span className="ema-type-secondary" style={{ lineHeight: 1.5 }}>
            Text secundar · 12,5/400 la 72% opacitate
          </span>
          <span className="ema-type-mono">GEIST MONO 11 · CIFRE, PAGINI, UNITĂŢI</span>
          <span className="ema-section-key" style={{ textTransform: 'none' }}>
            ANTET SECŢIUNE · 11 / .09em
          </span>
        </div>
      </SheetRow>

      <SheetRow label="RÂND TABEL">
        <div className="sheet-fill" role="table">
          <TableRow>
            <Cell grow>Recuperare căldură compresoare</Cell>
            <Cell width={80} figures>
              148 000
            </Cell>
            <Cell width={50} figures>
              212
            </Cell>
            <Cell width={90} end>
              <Status tone="ok">complet</Status>
            </Cell>
          </TableRow>
          <TableRow data-state="hover">
            <Cell grow>Variaţie turaţie pompe reţea</Cell>
            <Cell width={80} figures>
              96 000
            </Cell>
            <Cell width={50} figures>
              104
            </Cell>
            <Cell width={90} end>
              <Status tone="warn">lipseşte</Status>
            </Cell>
          </TableRow>
        </div>
      </SheetRow>

      <SheetRow label="CÂMPURI">
        <TextField defaultValue="Client B S.A." width={220} aria-label="Denumire" />
        <TextField
          defaultValue="4 218 kW"
          width={150}
          figures
          data-state="confirmed"
          aria-label="Putere"
        />
        <MissingField>necompletat</MissingField>
        <Select placeholder="Sursă de finanţare" aria-label="Sursă de finanţare">
          <option>Fonduri proprii</option>
        </Select>
      </SheetRow>

      <SheetRow label="WIDGET EMA">
        <EmaWidget
          title="Un singur îndemn, niciodată o listă"
          actions={
            <>
              <Button height={32}>Acţiune</Button>
              <Button variant="secondary" height={32}>
                Mai târziu
              </Button>
            </>
          }
        >
          Textul explică de ce, nu doar ce. Maxim două acţiuni.
        </EmaWidget>
      </SheetRow>

      <SheetRow label="RAZE & UMBRE">
        {[10, 14, 18].map((radius) => (
          <span key={radius} className="sheet-radius" style={{ borderRadius: radius }}>
            r {radius}
          </span>
        ))}
        <span
          className="sheet-radius sheet-radius--wide"
          style={{ background: 'var(--paper)', boxShadow: 'var(--shadow-paper)' }}
        >
          hârtie
        </span>
        <span
          className="sheet-radius sheet-radius--wide"
          style={{ background: 'var(--surface)', boxShadow: 'var(--shadow-dialog)' }}
        >
          dialog
        </span>
      </SheetRow>

      <SheetRow label="FOCUS">
        <Button className="ema-focus-ring">Primar focalizat</Button>
        <Button variant="secondary" className="ema-focus-ring">
          Secundar focalizat
        </Button>
        <TextField
          defaultValue="4 218 kW"
          width={150}
          figures
          data-state="focus"
          aria-label="Putere"
        />
        <ListRow boxed className="ema-focus-ring">
          Rând de listă focalizat
        </ListRow>
        <Legend small>inel 2px offset + 2px oliv · niciodată outline:none fără înlocuitor</Legend>
      </SheetRow>

      <SheetRow label="STĂRI BUTON">
        {buttonStates.map((state) => (
          <span key={state} className="sheet-stack">
            <Button
              data-state={state === 'hover' ? 'hover' : state === 'activ' ? 'active' : undefined}
              loading={state === 'încărcare'}
              disabled={state === 'dezactivat'}
            >
              Generează
            </Button>
            <Legend small>{state}</Legend>
          </span>
        ))}
        <Legend small>hover +8% lum · activ −6% · dezactivat fără umbră, fără cursor</Legend>
      </SheetRow>

      <SheetRow label="STĂRI RÂND">
        <div className="sheet-fill" style={{ gap: 3 }}>
          <ListRow>
            <span style={{ flex: 1 }}>normal — fond transparent, separator hairline</span>
            <Legend small>—</Legend>
          </ListRow>
          <ListRow data-state="hover">
            <span style={{ flex: 1 }}>hover — fond 5%</span>
            <Legend small>{inkRgba}</Legend>
          </ListRow>
          <ListRow selected>
            <span style={{ flex: 1 }}>selectat — oliv 12% + bară 2px la stânga</span>
            <Legend small>inset 2px 0 0</Legend>
          </ListRow>
        </div>
      </SheetRow>

      <SheetRow label="SPAŢIERE">
        {[6, 10, 14, 18, 26, 34, 44].map((space) => (
          <span key={space} className="sheet-stack">
            <span
              style={{
                width: `var(--space-${String(space)})`,
                height: 26,
                borderRadius: 3,
                background: 'var(--olive)',
              }}
            />
            <Legend small>{space}</Legend>
          </span>
        ))}
        <Legend small>scară pe 4 · 6 / 10 / 14 / 18 / 26 / 34 / 44</Legend>
      </SheetRow>

      <SheetRow label="PICTOGRAME">
        {iconSizes.map(([size, use]) => (
          <span key={size} className="sheet-stack">
            <span className="sheet-icon-box">
              <Icon icon={File} size={size} stroke={1.7} />
            </span>
            <Legend small>{size}px</Legend>
            <span className="sheet-caption-small">{use}</span>
          </span>
        ))}
        <Legend small>grosime 1,6–1,8 · capete rotunde · currentColor</Legend>
      </SheetRow>

      <SheetRow label="TOKENURI">
        <TokenTable theme={theme} />
      </SheetRow>

      <SheetRow label="GRILĂ">
        <span className="ema-type-secondary">
          Fereastră fixă 1400×900, aplicaţie desktop. Bară laterală 230, panou de activitate 290,
          conţinut restul cu padding 34. Spaţiere pe 4: 6 / 10 / 14 / 18 / 26 / 34.
        </span>
      </SheetRow>
    </SheetFrame>
  )
}
