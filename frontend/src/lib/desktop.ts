/** The file bridge exists only inside Ema's desktop window. */
type DesktopError = { ok: false; code: string; message: string }

export interface DesktopBridge {
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
