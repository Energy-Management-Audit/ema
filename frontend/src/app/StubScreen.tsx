import { AppSidebar } from './AppSidebar.tsx'
import { Content, Window } from '../ui/Shell.tsx'

export function StubScreen({
  title,
  current,
  activeJobId,
}: {
  title: string
  current?: 'home' | 'clients' | 'reporting'
  activeJobId?: string
}) {
  return (
    <Window>
      <AppSidebar current={current} activeJobId={activeJobId} />
      <Content crumb="" title={title}>
        <span />
      </Content>
    </Window>
  )
}
