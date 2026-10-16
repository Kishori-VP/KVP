
import { useEffect, useRef, useState } from 'react'
import {
  Bot,
  Database,
  Maximize2,
  Minimize2,
  RefreshCw,
  Send,
  Sparkles,
  X,
} from 'lucide-react'
import api, { errorMessage } from '../lib/api'

const WELCOME_MESSAGE =
  'Hi! Ask me anything about our programmes, field activities, villages, beneficiaries, targets, cases, events, or attendance. I answer using all database records across all programmes.'

function readableAnswer(value) {
  if (typeof value === 'string') return value.trim()

  // Handle LangChain content blocks if the API returns them directly.
  if (Array.isArray(value)) {
    return value
      .map((part) => {
        if (typeof part === 'string') return part
        if (part && typeof part.text === 'string') return part.text
        return ''
      })
      .filter(Boolean)
      .join('\n')
      .trim()
  }

  if (value && typeof value === 'object') {
    if (typeof value.answer === 'string') return readableAnswer(value.answer)
    if (typeof value.text === 'string') return value.text.trim()
  }

  return 'The assistant returned an unreadable response. Please try again.'
}

function cleanSources(sources) {
  if (!Array.isArray(sources)) return []
  const seen = new Set()

  return sources.filter((source) => {
    if (!source || typeof source.collection !== 'string') return false
    const key = `${source.collection}:${source.record_id || ''}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export default function AdminAssistant() {
  const [open, setOpen] = useState(false)
  const [minimized, setMinimized] = useState(false)
  const [status, setStatus] = useState(null)
  const [showDatabase, setShowDatabase] = useState(false)
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([
    { role: 'assistant', content: WELCOME_MESSAGE },
  ])
  const [busy, setBusy] = useState(false)
  const [reindexing, setReindexing] = useState(false)
  const [reindexProgress, setReindexProgress] = useState('')
  const [error, setError] = useState('')
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const pollTimerRef = useRef(null)

  function startPollingReindex() {
    if (pollTimerRef.current) return
    pollTimerRef.current = setInterval(async () => {
      try {
        const res = await api.get('/ai/reindex/status')
        const data = res.data || {}
        if (data.is_running) {
          setReindexing(true)
          const pct = data.total > 0 ? Math.round((data.progress / data.total) * 100) : 0
          setReindexProgress(
            data.total > 0
              ? `${data.progress}/${data.total} (${pct}%)`
              : 'Indexing…'
          )
        } else {
          clearInterval(pollTimerRef.current)
          pollTimerRef.current = null
          setReindexing(false)
          setReindexProgress('')
          await loadStatus()
          if (data.message && data.message !== 'Idle' && data.message !== 'Ready') {
            setMessages((previous) => [
              ...previous,
              {
                role: 'assistant',
                content: data.message,
              },
            ])
          }
        }
      } catch {
        // network blip during polling, keep polling
      }
    }, 1500)
  }

  async function loadStatus() {
    try {
      const response = await api.get('/ai/status')
      setStatus(response.data)
      setError('')
      if (response.data?.is_reindexing) {
        setReindexing(true)
        startPollingReindex()
      }
      return response.data
    } catch (err) {
      setError(errorMessage(err))
      return null
    }
  }

  useEffect(() => {
    loadStatus()
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current)
    }
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'end',
    })
  }, [messages, busy, open, showDatabase, reindexing])

  useEffect(() => {
    if (open && !minimized) {
      const timer = setTimeout(() => inputRef.current?.focus(), 80)
      return () => clearTimeout(timer)
    }
  }, [open, minimized])

  async function handleReindex(force = false) {
    if (reindexing) return

    setReindexing(true)
    setReindexProgress(force ? 'Rebuilding…' : 'Checking…')
    setError('')

    try {
      const response = await api.post(`/ai/reindex${force ? '?force=true' : ''}`)
      const result = response.data || {}
      if (result.message) {
        setMessages((previous) => [
          ...previous,
          {
            role: 'assistant',
            content: result.message,
          },
        ])
      }
      startPollingReindex()
    } catch (err) {
      setReindexing(false)
      setReindexProgress('')
      setError(errorMessage(err))
    }
  }

  async function handleSend(event) {
    event?.preventDefault()

    const prompt = question.trim()
    if (!prompt || busy) return

    const history = [
      ...messages,
      { role: 'user', content: prompt },
    ]

    setMessages(history)
    setQuestion('')
    setBusy(true)
    setError('')

    try {
      const response = await api.post('/ai/chat', {
        question: prompt,
        history: history
          .slice(-7)
          .map(({ role, content }) => ({ role, content })),
      })

      const data = response.data || {}
      const answer = readableAnswer(data.answer)

      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          content: answer,
          sources: cleanSources(data.sources),
        },
      ])
    } catch (err) {
      setError(errorMessage(err))
      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          content:
            'I could not complete that request. Check the error shown below and try again.',
        },
      ])
    } finally {
      setBusy(false)
    }
  }

  function closeAssistant() {
    setOpen(false)
    setMinimized(false)
    setShowDatabase(false)
    setQuestion('')
    setError('')
    setMessages([{ role: 'assistant', content: WELCOME_MESSAGE }])
  }

  function toggleAssistant() {
    if (minimized) {
      setMinimized(false)
      setOpen(true)
      return
    }

    if (open) {
      closeAssistant()
      return
    }

    setOpen(true)
    setMinimized(false)
  }

  return (
    <div className="fixed bottom-4 right-4 z-[80]">
      {open && !minimized && (
        <section
          role="dialog"
          aria-label="Ask AI"
          className="mb-3 flex h-[min(620px,calc(100dvh-100px))] w-[min(410px,calc(100vw-24px))] flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl ring-1 ring-black/5 sm:h-[600px]"
        >
          <header className="flex shrink-0 items-center gap-3 bg-brand-700 px-4 py-3 text-white">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/15">
              <Bot className="h-5 w-5" />
            </div>

            <div className="min-w-0 flex-1">
              <div className="font-semibold">Ask AI</div>
              <div className="text-xs text-white/75">
                All programmes & database assistant
              </div>
            </div>

            <button
              type="button"
              onClick={() => {
                setShowDatabase((current) => !current)
                loadStatus()
              }}
              title="Open database and index details"
              aria-label="Open database and index details"
              aria-expanded={showDatabase}
              className={`rounded-lg p-2 hover:bg-white/15 ${
                showDatabase ? 'bg-white/20' : ''
              }`}
            >
              <Database className="h-4 w-4" />
            </button>

            <button
              type="button"
              onClick={() => setMinimized(true)}
              title="Minimize assistant"
              aria-label="Minimize assistant"
              className="rounded-lg p-2 hover:bg-white/15"
            >
              <Minimize2 className="h-4 w-4" />
            </button>

            <button
              type="button"
              onClick={closeAssistant}
              title="Close assistant and clear conversation"
              aria-label="Close assistant"
              className="rounded-lg p-2 hover:bg-white/15"
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          {showDatabase && (
            <div className="shrink-0 border-b border-blue-100 bg-blue-50 px-4 py-3 text-xs text-blue-950">
              <div className="mb-2 flex items-center justify-between">
                <strong>Knowledge database</strong>
                <button
                  type="button"
                  onClick={() => setShowDatabase(false)}
                  className="rounded px-2 py-1 hover:bg-blue-100"
                >
                  Hide
                </button>
              </div>

              <div>
                Indexed chunks:{' '}
                <strong>{status?.indexed_chunks ?? 'Unknown'}</strong>
              </div>
              <div>
                Retrieval mode:{' '}
                <strong>{status?.retrieval_mode || 'Unknown'}</strong>
              </div>
              <div>
                Chat model:{' '}
                <strong>{status?.model || 'Unknown'}</strong>
              </div>
              <div>
                API configured:{' '}
                <strong>{status?.configured ? 'Yes' : 'No'}</strong>
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => handleReindex(false)}
                  disabled={reindexing || !status?.configured}
                  className="rounded border border-blue-300 bg-white px-2.5 py-1 font-semibold text-blue-900 shadow-sm hover:bg-blue-100 disabled:opacity-50"
                  title="Check database for newly added or modified data"
                >
                  {reindexing ? 'Syncing…' : 'Sync New Data'}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm('Do you want to force a full re-index of all records?')) {
                      handleReindex(true)
                    }
                  }}
                  disabled={reindexing || !status?.configured}
                  className="rounded border border-gray-300 bg-white px-2 py-1 text-gray-700 hover:bg-gray-100 disabled:opacity-50"
                  title="Force a complete rebuild from scratch"
                >
                  Full Rebuild
                </button>

                <button
                  type="button"
                  onClick={loadStatus}
                  className="rounded border border-blue-200 bg-white px-2 py-1 text-blue-800 hover:bg-blue-100"
                >
                  Refresh
                </button>
              </div>
            </div>
          )}

          <div className="flex shrink-0 items-center justify-between gap-2 border-b border-gray-100 bg-gray-50 px-4 py-2 text-[11px] text-gray-500">
            <span className="truncate">
              {reindexing ? (
                <span className="font-medium text-brand-700 animate-pulse">
                  ⚡ {reindexProgress ? `Syncing: ${reindexProgress}` : 'Syncing database…'}
                </span>
              ) : status ? (
                `${status.indexed_chunks || 0} chunks · ${
                  status.configured ? 'Assistant ready' : 'AI not configured'
                } · ${status.retrieval_mode || 'unknown'} retrieval`
              ) : (
                'Checking assistant status…'
              )}
            </span>

            <button
              type="button"
              onClick={() => handleReindex(false)}
              disabled={reindexing || !status?.configured}
              className="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 font-medium text-brand-700 hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-50"
              title="Check database and add newly added data"
            >
              <RefreshCw
                className={`h-3 w-3 ${reindexing ? 'animate-spin' : ''}`}
              />
              {reindexing ? (reindexProgress || 'Syncing…') : 'Sync Data'}
            </button>
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto bg-gray-50/70 p-3">
            {messages.map((message, index) => (
              <div
                key={`${index}-${message.role}`}
                className={`max-w-[92%] rounded-2xl px-3 py-2.5 text-sm leading-relaxed ${
                  message.role === 'user'
                    ? 'ml-auto rounded-br-md bg-brand-700 text-white'
                    : 'rounded-bl-md border border-gray-100 bg-white text-gray-800 shadow-sm'
                }`}
              >
                {message.role === 'assistant' && (
                  <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-brand-700">
                    <Sparkles className="h-3 w-3" />
                    Ask AI
                  </div>
                )}

                <div className="whitespace-pre-wrap break-words">
                  {readableAnswer(message.content)}
                </div>

                {message.sources?.length > 0 && (
                  <div className="mt-2 border-t border-gray-100 pt-2 text-[10px] text-gray-500">
                    Sources:{' '}
                    {[
                      ...new Set(message.sources.map((source) => source.collection)),
                    ].join(', ')}
                  </div>
                )}
              </div>
            ))}

            {busy && (
              <div className="w-fit rounded-xl border border-gray-100 bg-white px-3 py-2 text-xs text-gray-500 shadow-sm">
                <span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-brand-600" />
                Searching database records…
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {error && (
            <div
              role="alert"
              className="mx-3 mt-2 max-h-24 overflow-y-auto rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
            >
              {error}
            </div>
          )}

          <form
            onSubmit={handleSend}
            className="flex shrink-0 items-end gap-2 border-t border-gray-100 bg-white p-3"
          >
            <textarea
              ref={inputRef}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  handleSend()
                }
              }}
              rows={1}
              maxLength={2000}
              placeholder="Ask about any programme or data…"
              aria-label="Ask AI"
              className="max-h-24 min-h-10 min-w-0 flex-1 resize-y rounded-xl border border-gray-200 px-3 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
            />

            <button
              type="submit"
              disabled={busy || !question.trim()}
              aria-label="Send message"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-700 text-white hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>

          <div className="shrink-0 px-3 pb-2 text-center text-[10px] text-gray-400">
            Verify important records against the source data.
          </div>
        </section>
      )}

      <button
        type="button"
        onClick={toggleAssistant}
        aria-label={
          minimized
            ? 'Restore Ask AI'
            : open
              ? 'Close Ask AI'
              : 'Open Ask AI'
        }
        aria-expanded={open && !minimized}
        className="ml-auto flex h-14 items-center gap-2 rounded-full bg-brand-700 px-4 text-white shadow-xl transition hover:-translate-y-0.5 hover:bg-brand-800 focus:outline-none focus:ring-4 focus:ring-brand-200"
      >
        {minimized ? (
          <Maximize2 className="h-5 w-5" />
        ) : open ? (
          <X className="h-5 w-5" />
        ) : (
          <Bot className="h-6 w-6" />
        )}

        <span className="text-sm font-semibold">
          {minimized
            ? 'Restore Ask AI'
            : open
              ? 'Close Ask AI'
              : 'Ask AI'}
        </span>
      </button>
    </div>
  )
}
