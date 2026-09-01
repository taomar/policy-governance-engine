import { useEffect, useRef, useState } from 'react'

import { INTEGRATION } from '../copy/strings'
import {
  buildIntegrationCurl,
  buildIntegrationHttp,
  buildIntegrationPython,
} from '../lib/integrationGuide'
import { isParsableUrl, joinUrl } from '../lib/requestBody'
import { CodeBlock } from './CodeBlock'

type GuideTab = 'agents' | 'curl' | 'python' | 'http'

interface IntegrationGuideProps {
  open: boolean
  baseUrl: string
  projectKey: string
  onClose: () => void
  onAnnounce: (message: string) => void
}

const TABS: Array<{ id: GuideTab; label: string }> = [
  { id: 'agents', label: 'Agents & Copilot' },
  { id: 'curl', label: 'cURL' },
  { id: 'python', label: 'Python' },
  { id: 'http', label: 'REST & OpenAPI' },
]

export function IntegrationGuide(props: IntegrationGuideProps) {
  const [active, setActive] = useState<GuideTab>('agents')
  const closeRef = useRef<HTMLButtonElement | null>(null)
  const dialogRef = useRef<HTMLElement | null>(null)
  const returnFocusRef = useRef<HTMLElement | null>(null)
  const target = { baseUrl: props.baseUrl, projectKey: props.projectKey }

  useEffect(() => {
    if (!props.open) return
    returnFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    closeRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') props.onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      returnFocusRef.current?.focus()
    }
  }, [props.open, props.onClose])

  if (!props.open) return null

  const docsReady = isParsableUrl(props.baseUrl)
  const openApiUrl = docsReady ? joinUrl(props.baseUrl, '/openapi.json') : null
  const swaggerUrl = docsReady ? joinUrl(props.baseUrl, '/docs') : null

  return (
    <div
      className="guide-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) props.onClose()
      }}
    >
      <section
        ref={dialogRef}
        className="integration-guide"
        role="dialog"
        aria-modal="true"
        aria-labelledby="integration-guide-title"
        data-testid="playground-integration-guide"
        onKeyDown={(event) => {
          if (event.key !== 'Tab') return
          const focusable = Array.from(
            dialogRef.current?.querySelectorAll<HTMLElement>(
              'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
            ) ?? [],
          )
          if (focusable.length === 0) return
          const first = focusable[0]
          const last = focusable[focusable.length - 1]
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault()
            last.focus()
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault()
            first.focus()
          }
        }}
      >
        <header className="integration-guide__header">
          <div>
            <span className="eyebrow">External integration</span>
            <h2 id="integration-guide-title">{INTEGRATION.title}</h2>
            <p>{INTEGRATION.intro}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="btn"
            aria-label={INTEGRATION.close}
            onClick={props.onClose}
          >
            Close
          </button>
        </header>

        <div className="integration-guide__modes">
          <article>
            <span className="pill">Option 1</span>
            <h3>{INTEGRATION.decisionHeading}</h3>
            <p>{INTEGRATION.decisionBody}</p>
            <code>/api/policy-decisions/{'{project_key}'}/case</code>
          </article>
          <article>
            <span className="pill">Option 2</span>
            <h3>{INTEGRATION.decisionLightHeading}</h3>
            <p>{INTEGRATION.decisionLightBody}</p>
            <code>/api/policy-decisions/{'{project_key}'}/case/light</code>
          </article>
          <article>
            <span className="pill">Option 3</span>
            <h3>{INTEGRATION.policiesHeading}</h3>
            <p>{INTEGRATION.policiesBody}</p>
            <code>/api/policy-decisions/{'{project_key}'}/policies</code>
          </article>
        </div>

        <div className="integration-guide__tabs" role="tablist" aria-label="Integration examples">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={active === tab.id}
              className={active === tab.id ? 'is-active' : ''}
              onClick={() => setActive(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="integration-guide__panel" role="tabpanel">
          {active === 'agents' ? (
            <div className="integration-guide__agent" data-testid="integration-agent-guide">
              <h3>{INTEGRATION.agentHeading}</h3>
              <p>{INTEGRATION.agentBody}</p>
              <ol>
                <li>Import the OpenAPI schema into the tool or connector definition.</li>
                <li>Keep all three operations separate so policy retrieval is never presented as a verdict.</li>
                <li>Store the subscription key in the agent host or connection secret store.</li>
                <li>
                  For decision JSON, read <code>outcome</code> before <code>information</code> or{' '}
                  <code>verdict</code>. For policy JSON, pass <code>policies</code> to your own agent.
                </li>
              </ol>
              <div className="btn-row">
                {openApiUrl ? (
                  <a className="btn btn--primary" href={openApiUrl} target="_blank" rel="noreferrer">
                    Open OpenAPI JSON
                  </a>
                ) : (
                  <span className="muted small">Enter a valid API base URL to open its schema.</span>
                )}
                {swaggerUrl ? (
                  <a className="btn" href={swaggerUrl} target="_blank" rel="noreferrer">
                    Open Swagger UI
                  </a>
                ) : null}
              </div>
            </div>
          ) : null}

          {active === 'curl' ? (
            <CodeBlock
              text={buildIntegrationCurl(target)}
              language="Shell"
              what="the cURL integration examples"
              downloadName="policy-api-examples.sh"
              onAnnounce={props.onAnnounce}
            />
          ) : null}

          {active === 'python' ? (
            <CodeBlock
              text={buildIntegrationPython(target)}
              language="Python"
              what="the Python integration examples"
              downloadName="policy_api_examples.py"
              onAnnounce={props.onAnnounce}
            />
          ) : null}

          {active === 'http' ? (
            <CodeBlock
              text={buildIntegrationHttp(target)}
              language="HTTP"
              what="the raw REST integration examples"
              downloadName="policy-api-examples.http"
              downloadMime="text/plain"
              onAnnounce={props.onAnnounce}
            />
          ) : null}
        </div>
      </section>
    </div>
  )
}
