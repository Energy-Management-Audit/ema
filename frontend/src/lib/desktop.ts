/** The file bridge exists only inside Ema's desktop window. */
type DesktopError = { ok: false; code: string; message: string }

export interface DesktopBridge {
  choose_folder(): Promise<{ path: string } | null>
  save_output(
    jobId: string,
    outputId: string,
  ): Promise<{ ok: true; result: 'saved' | 'cancelled' } | DesktopError>
  open_output(
    jobId: string,
    outputId: string,
  ): Promise<{ ok: true; result: 'opened' } | DesktopError>
}

export function desktopApi(): DesktopBridge | null {
  const bridge = (window as Window & { pywebview?: { api?: Partial<DesktopBridge> } }).pywebview
    ?.api
  return typeof bridge?.save_output === 'function' && typeof bridge.open_output === 'function'
    ? (bridge as DesktopBridge)
    : null
}

/** Browser exports use the workspace default; closing the desktop picker cancels the action. */
export async function chooseExportFolder(): Promise<{ path: string | null } | null> {
  const desktop = (window as Window & { pywebview?: { api?: Partial<DesktopBridge> } }).pywebview
  if (!desktop) return { path: null }
  if (typeof desktop.api?.choose_folder !== 'function') throw new Error('choose_folder unavailable')
  return desktop.api.choose_folder()
}
