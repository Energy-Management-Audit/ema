import { Button } from '../ui/Button'
import { Dialog, FileNotice } from '../ui/Dialog'

/** DG1 (7c): the draft was edited in Word; generating again makes a new version, the edited file
 * stays. Outputs are immutable, so there is no „Suprascrie” (§5.18). */
export function RegenerateDialog({
  name,
  onClose,
  onConfirm,
}: {
  name: string
  onClose: () => void
  onConfirm: () => void
}) {
  return (
    <Dialog
      title="Raportul Word există deja"
      onClose={onClose}
      content={<FileNotice name={name} detail="editat în afara Ema" />}
      actions={
        <>
          <Button variant="secondary" height={36} onClick={onClose}>
            Renunţă
          </Button>
          <Button height={36} onClick={onConfirm}>
            Salvează ca versiune nouă
          </Button>
        </>
      }
    >
      Ai editat ciorna în Word după ce a fost generată. Dacă generez din nou, versiunea nouă nu
      conţine modificările tale; fişierul editat rămâne.
    </Dialog>
  )
}
