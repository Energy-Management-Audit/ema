export function navigate(to: string, replace = false): void {
  if (to === location.pathname + location.search) return
  if (replace) history.replaceState(null, '', to)
  else history.pushState(null, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
}
