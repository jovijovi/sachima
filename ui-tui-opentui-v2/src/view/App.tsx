/**
 * App — the Solid view shell (spec v4 §2 `view/App.tsx`). Header + a content zone
 * that is either the PAGER overlay (long slash output) or the normal
 * transcript + input zone; the input zone is one of: blocking prompt, session
 * switcher, generic picker (model/skills), or the composer. Fully themed (§7.5).
 *
 *   header     flexShrink:0            (top chrome line)
 *   content    flexGrow:1, minHeight:0 — Pager OR (transcript + input zone)
 *   transcript flexGrow:1, minHeight:0 (the one <scrollbox>; §8 #2 gotchas)
 *   input zone flexShrink:0            (PromptOverlay | SessionSwitcher | Picker | Composer)
 *
 * Overlays REPLACE rather than stack (a `<Switch>`), so the composer remounts +
 * refocuses when an overlay closes; the key that closed an overlay can't leak
 * into it because the close is deferred a tick.
 */
import { Match, Switch } from 'solid-js'

import type { PromptHistory } from '../logic/history.ts'
import type { SessionStore } from '../logic/store.ts'
import { Composer } from './composer.tsx'
import { Header } from './header.tsx'
import { AgentsDashboard } from './overlays/agentsDashboard.tsx'
import { Pager } from './overlays/pager.tsx'
import { Picker } from './overlays/picker.tsx'
import { SessionSwitcher } from './overlays/sessionSwitcher.tsx'
import { PromptOverlay } from './prompts/promptOverlay.tsx'
import { StatusBar } from './statusBar.tsx'
import { StatusLine } from './statusLine.tsx'
import { useTheme } from './theme.tsx'
import { Transcript } from './transcript.tsx'

export interface AppProps {
  readonly store: SessionStore
  readonly onSubmit?: (text: string) => void
  readonly onType?: (text: string) => void
  readonly onRespond?: (method: string, params: Record<string, unknown>) => void
  readonly onResume?: (sessionId: string) => void
  readonly sessionId?: () => string | undefined
  readonly history?: PromptHistory
  readonly onImagePaste?: () => void
}

const NOOP = () => {}
const NOOP_RESPOND = () => {}
const NOOP_RESUME = () => {}
const NO_SESSION = () => undefined

export function App(props: AppProps) {
  const theme = useTheme()
  const blocked = () => props.store.state.prompt !== undefined
  const pager = () => props.store.state.pager
  const dashboard = () => props.store.state.dashboard
  const switcher = () => props.store.state.switcher
  const picker = () => props.store.state.picker
  // Defer the close so the key that closed an overlay (Esc/q/Enter) can't land in
  // the freshly-remounted composer.
  const closePager = () => setTimeout(() => props.store.closePager(), 0)
  const closeDashboard = () => setTimeout(() => props.store.closeDashboard(), 0)
  const closeSwitcher = () => setTimeout(() => props.store.closeSwitcher(), 0)
  const closePicker = () => setTimeout(() => props.store.closePicker(), 0)
  const resume = (id: string) => {
    ;(props.onResume ?? NOOP_RESUME)(id)
    closeSwitcher()
  }

  return (
    <box style={{ flexDirection: 'column', flexGrow: 1, paddingTop: 1, paddingLeft: 1, paddingRight: 1 }}>
      <Header store={props.store} />
      {/* content zone: a full-screen overlay (pager / agents dashboard) OR the transcript + input zone */}
      <Switch
        fallback={
          <>
            <Transcript store={props.store} />
            {/* transient busy face floats at the bottom of the transcript area */}
            <StatusLine store={props.store} />
            {/* input region — a top-edge rule separates the status bar + textbox from the
                transcript above; the status bar sits directly ABOVE the composer (item 14). */}
            <box
              border={['top']}
              borderColor={theme().color.border}
              style={{ flexShrink: 0, flexDirection: 'column' }}
            >
              <StatusBar store={props.store} />
              <Switch
                fallback={
                  <Composer
                    onSubmit={props.onSubmit ?? NOOP}
                    onType={props.onType}
                    completions={() => props.store.state.completions ?? []}
                    completionFrom={() => props.store.state.completionFrom}
                    onDismiss={() => props.store.clearCompletions()}
                    history={props.history}
                    onImagePaste={props.onImagePaste}
                  />
                }
              >
                <Match when={blocked()}>
                  <PromptOverlay
                    store={props.store}
                    onRespond={props.onRespond ?? NOOP_RESPOND}
                    sessionId={props.sessionId ?? NO_SESSION}
                  />
                </Match>
                <Match when={switcher()}>
                  {sessions => <SessionSwitcher sessions={sessions()} onPick={resume} onClose={closeSwitcher} />}
                </Match>
                <Match when={picker()}>
                  {p => (
                    <Picker
                      title={p().title}
                      items={p().items}
                      onPick={value => {
                        p().onPick(value)
                        closePicker()
                      }}
                      onClose={closePicker}
                    />
                  )}
                </Match>
              </Switch>
            </box>
          </>
        }
      >
        <Match when={pager()}>{p => <Pager title={p().title} text={p().text} onClose={closePager} />}</Match>
        <Match when={dashboard()}>
          <AgentsDashboard subagents={props.store.state.subagents} onClose={closeDashboard} />
        </Match>
      </Switch>
    </box>
  )
}
