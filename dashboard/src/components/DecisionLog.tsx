import { useState, useRef, useEffect, type ReactNode } from 'react'
import { Brain, Loader2, Send, Sparkles, Wrench, Clock, ChevronDown, ChevronRight } from 'lucide-react'
import { type ChatExecutionResult, type ChatResponse } from '../hooks/useApi'

interface DecisionLogProps {
  onDevicesChanged: () => void
  onChatResult?: (message: string, result: ChatResponse) => void
  sendMessageRef?: React.MutableRefObject<((text: string) => void) | null>
}

export interface LiveTrace {
  timestamp: string
  message: string
  result: ChatResponse
}

export interface AgentEvent {
  type: 'chunk' | 'action' | 'observation' | 'reply' | 'status' | 'error' | 'thought'
  content?: string
  tool?: string
  args?: Record<string, unknown>
  result?: string
  step?: number
  done?: boolean
  execution_results?: ChatExecutionResult[]
}

interface BrainEvent {
  type: string
  timestamp?: string
  skill?: string
  goal?: string
  reason?: string
  device_id?: string
  action?: string
  params?: Record<string, unknown>
  verification_passed?: boolean | null
  final_status?: string
}

interface ConversationTurn {
  id: string
  timestamp: string
  userMessage: string
  result: ChatResponse
  trace: AgentEvent[]
  qrImage?: string
  qrPolling?: boolean
  isProactive?: boolean
  statusText?: string
}

function formatTime(ts?: string) {
  if (!ts) return '--:--'
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return '--:--'
  }
}

function renderInline(text: string): ReactNode[] {
  // Handle **bold**, *italic*, `code`, [link](url)
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g)
  return parts.filter(Boolean).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**'))
      return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>
    if (part.startsWith('*') && part.endsWith('*'))
      return <em key={i}>{part.slice(1, -1)}</em>
    if (part.startsWith('`') && part.endsWith('`'))
      return <code key={i} className="px-1 py-0.5 rounded bg-slate-100 text-violet-700 font-mono text-[12px]">{part.slice(1, -1)}</code>
    const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
    if (linkMatch)
      return <a key={i} href={linkMatch[2]} target="_blank" rel="noopener noreferrer" className="text-violet-600 underline underline-offset-2 hover:text-violet-800">{linkMatch[1]}</a>
    return <span key={i}>{part}</span>
  })
}

function MarkdownMessage({ content }: { content: string }) {
  const lines = content.split('\n')
  const blocks: ReactNode[] = []
  let i = 0

  while (i < lines.length) {
    const raw = lines[i]
    const line = raw.trimEnd()

    // Fenced code block
    if (line.startsWith('```')) {
      const lang = line.slice(3).trim()
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].trimEnd().startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      blocks.push(
        <div key={`code-${i}`} className="my-2 rounded-xl overflow-hidden border border-slate-200">
          {lang && <div className="px-3 py-1 bg-slate-100 text-[10px] font-mono text-slate-500 border-b border-slate-200">{lang}</div>}
          <pre className="p-3 bg-slate-50 text-xs font-mono text-slate-700 overflow-x-auto leading-5 whitespace-pre">{codeLines.join('\n')}</pre>
        </div>
      )
      i++
      continue
    }

    // Horizontal rule
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) {
      blocks.push(<hr key={`hr-${i}`} className="my-2 border-slate-200" />)
      i++; continue
    }

    // Headings
    const h3 = line.match(/^###\s+(.+)/)
    if (h3) { blocks.push(<h3 key={`h3-${i}`} className="text-sm font-bold text-slate-800 mt-2 mb-1">{renderInline(h3[1])}</h3>); i++; continue }
    const h2 = line.match(/^##\s+(.+)/)
    if (h2) { blocks.push(<h2 key={`h2-${i}`} className="text-base font-bold text-slate-800 mt-2 mb-1">{renderInline(h2[1])}</h2>); i++; continue }
    const h1 = line.match(/^#\s+(.+)/)
    if (h1) { blocks.push(<h1 key={`h1-${i}`} className="text-lg font-bold text-slate-800 mt-2 mb-1">{renderInline(h1[1])}</h1>); i++; continue }

    // Blockquote
    if (line.startsWith('> ')) {
      const quoteLines: string[] = []
      while (i < lines.length && lines[i].trimEnd().startsWith('> ')) {
        quoteLines.push(lines[i].trimEnd().slice(2))
        i++
      }
      blocks.push(
        <blockquote key={`bq-${i}`} className="my-1.5 pl-3 border-l-2 border-violet-300 text-slate-500 italic text-sm">
          {quoteLines.map((l, j) => <p key={j}>{renderInline(l)}</p>)}
        </blockquote>
      )
      continue
    }

    // Unordered list
    if (/^[-*+]\s/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^[-*+]\s/.test(lines[i].trimEnd())) {
        items.push(lines[i].trimEnd().replace(/^[-*+]\s/, ''))
        i++
      }
      blocks.push(
        <ul key={`ul-${i}`} className="my-1.5 ml-4 space-y-0.5 list-disc text-sm text-slate-700">
          {items.map((item, j) => <li key={j}>{renderInline(item)}</li>)}
        </ul>
      )
      continue
    }

    // Ordered list
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\d+\.\s/.test(lines[i].trimEnd())) {
        items.push(lines[i].trimEnd().replace(/^\d+\.\s/, ''))
        i++
      }
      blocks.push(
        <ol key={`ol-${i}`} className="my-1.5 ml-4 space-y-0.5 list-decimal text-sm text-slate-700">
          {items.map((item, j) => <li key={j}>{renderInline(item)}</li>)}
        </ol>
      )
      continue
    }

    // Table
    if (line.includes('|') && i + 1 < lines.length && lines[i + 1].includes('---')) {
      const headers = line.split('|').map(h => h.trim()).filter(Boolean)
      i += 2 // skip header + separator
      const rows: string[][] = []
      while (i < lines.length && lines[i].includes('|')) {
        rows.push(lines[i].split('|').map(c => c.trim()).filter(Boolean))
        i++
      }
      blocks.push(
        <div key={`table-${i}`} className="my-2 overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>{headers.map((h, j) => <th key={j} className="px-3 py-2 font-semibold text-slate-600">{renderInline(h)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={ri} className={ri % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                  {row.map((cell, ci) => <td key={ci} className="px-3 py-2 text-slate-700 border-t border-slate-100">{renderInline(cell)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
      continue
    }

    // Empty line
    if (!line.trim()) { i++; continue }

    // Paragraph
    blocks.push(<p key={`p-${i}`} className="text-sm leading-6 text-slate-700">{renderInline(line)}</p>)
    i++
  }

  return <div className="space-y-1">{blocks}</div>
}

function ExecutionSummaryCard({ items }: { items: ChatExecutionResult[] }) {
  return (
    <div className="rounded-2xl rounded-tl-md border border-emerald-200/80 bg-emerald-50 px-4 py-3">
      <div className="flex items-center gap-2 mb-2">
        <div className="flex items-center justify-center w-5 h-5 rounded-md bg-emerald-100">
          <Wrench className="h-3 w-3 text-emerald-600" />
        </div>
        <span className="text-[10px] font-semibold text-emerald-700 uppercase tracking-widest">已执行</span>
      </div>
      <div className="space-y-1">
        {items.map((item, i) => (
          <div key={i}>
            {item.actions.map((action, j) => (
              <p key={j} className="text-xs text-emerald-800 font-medium">
                {formatActionSummary(action.action, item.plan_item.skill_name, action.device_id, action.params)}
              </p>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

function formatActionSummary(action: string, skillName: string, deviceId: string, params: Record<string, unknown>): string {
  const device = deviceId.replace(/^miot_/, '').replace(/_/g, ' ')
  if (action === 'on' || action === 'turn_on') return `已开启 ${device}`
  if (action === 'off' || action === 'turn_off') return `已关闭 ${device}`
  if (action === 'set_brightness') return `已调节亮度 → ${params.value ?? params.brightness}%`
  if (action === 'set_color_temp') return `已调节色温 → ${params.kelvin ?? params.value}K`
  if (action === 'set_mode') return `已切换模式 → ${params.mode}`
  if (action === 'set_humidity' || action === 'set_target_humidity') {
    const value = params.value ?? params.humidity ?? params.target_humidity ?? params.relative_humidity
    return value == null ? `已设置目标湿度` : `已设置目标湿度 → ${value}%`
  }
  if (action === 'set_temperature' || action === 'set_target_temperature') {
    const value = params.value ?? params.temperature ?? params.target_temperature
    return value == null ? `已设置温度` : `已设置温度 → ${value}°C`
  }
  return `${skillName}: ${action} → ${device}`
}

function normalizeAutoText(text?: string) {
  if (!text) return ''
  return text
    .replace(/Turn on ([\w\s-]+) and maintain (\d+)% target humidity in auto mode/i, '已开启$1，并以自动模式维持目标湿度 $2%')
    .replace(/Current indoor humidity is ([\d.]+)%?,?\s+which is below (?:the |user )?confirmed ([\d.]+)% comfort humidity threshold,?/i, '当前室内湿度为 $1%，低于用户确认的 $2% 舒适湿度阈值，')
    .replace(/the humidifier is online and currently powered off,?\s*/i, '加湿器在线且当前处于关闭状态，')
    .replace(/The humidifier is currently powered off, online, and automatic activation aligns with the user's comfort-first policy and permission for automatic adjustment when humidity drops below (\d+)%\.?/i, '加湿器当前在线且处于关闭状态；自动开启符合用户的舒适优先策略，以及湿度低于 $1% 时允许自动调节的偏好。')
    .replace(/automatic activation aligns with the user's\s*/i, '自动开启符合用户的')
    .replace(/Mijia Smart Anti-bacterial Humidifier 2/gi, '米家智能除菌加湿器 2')
    .replace(/comfort-first policy/gi, '舒适优先策略')
    .replace(/confirmed ([\d.]+)% comfort humidity threshold/gi, '用户确认的 $1% 舒适湿度阈值')
    .replace(/target humidity/gi, '目标湿度')
    .replace(/auto mode/gi, '自动模式')
    .replace(/([，。；])\s+/g, '$1')
}

function formatVerificationStatus(status?: string, passed?: boolean | null) {
  if (!status) return ''
  if (status === 'verified') return '\n\n状态：已验证'
  if (status === 'unverifiable_but_executed') return '\n\n状态：已执行，设备未上报可验证状态'
  return `\n\n状态：\`${status}\`${passed === false ? '，未通过验证' : ''}`
}

export default function DecisionLog({ onDevicesChanged, onChatResult, sendMessageRef }: DecisionLogProps) {
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [conversation, setConversation] = useState<ConversationTurn[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)

  // Subscribe to proactive brain events via SSE
  useEffect(() => {
    const es = new EventSource('/api/brain/events')
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as BrainEvent
        if (data.type === 'proactive_action' && (data.goal || data.action)) {
          const turnId = `brain-${Date.now()}`
          const title = data.action && data.device_id
            ? formatActionSummary(data.action, data.skill || 'system', data.device_id, data.params || {})
            : normalizeAutoText(data.goal) || '系统自动执行'
          const reason = normalizeAutoText(data.reason)
          const status = formatVerificationStatus(data.final_status, data.verification_passed)
          const reply = `**自动执行**：${title}${reason ? `\n\n> ${reason}` : ''}${status}`
          setConversation(prev => [...prev, {
            id: turnId,
            timestamp: data.timestamp || new Date().toISOString(),
            userMessage: '',
            result: { reply },
            trace: [],
            qrImage: '',
            qrPolling: false,
            isProactive: true,
          }])
          onDevicesChanged()
        }
      } catch { /* ignore */ }
    }
    return () => es.close()
  }, [onDevicesChanged])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversation])

  // Expose send function to parent via ref (for VoiceOrb)
  useEffect(() => {
    if (!sendMessageRef) return
    sendMessageRef.current = (text: string) => {
      void handleSendWithText(text)
    }
    return () => { if (sendMessageRef) sendMessageRef.current = null }
  })

  const updateConversation = (id: string, updater: (turn: ConversationTurn) => ConversationTurn) => {
    setConversation((items) => items.map((item) => (item.id === id ? updater(item) : item)))
  }

  const handleSend = async () => {
    const text = message.trim()
    if (!text || sending) return
    await handleSendWithText(text)
  }

  const handleSendWithText = async (text: string) => {
    if (!text.trim() || sending) return

    setSending(true)
    setMessage('')
    const turnId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const timestamp = new Date().toISOString()

    setConversation((items) => [...items, {
      id: turnId, timestamp, userMessage: text,
      result: { reply: '' }, trace: [], qrImage: '', qrPolling: false,
    }])

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, stream: true }),
      })

      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let streamedReply = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (!raw) continue
          try {
            const parsed = JSON.parse(raw) as AgentEvent & { done?: boolean; reply?: string; error?: string }

            // Streaming text chunks (chitchat or ReAct final reply)
            if (parsed.type === 'chunk' && parsed.content) {
              streamedReply += parsed.content
              updateConversation(turnId, (turn) => ({
                ...turn,
                result: { ...turn.result, reply: streamedReply },
                statusText: undefined,
              }))
            }

            // Status update — show progress to user
            if (parsed.type === 'status' && parsed.content) {
              updateConversation(turnId, (turn) => ({
                ...turn,
                statusText: parsed.content,
              }))
            }

            // ReAct action/observation — append to trace
            if (parsed.type === 'action' || parsed.type === 'observation') {
              updateConversation(turnId, (turn) => ({
                ...turn,
                trace: [...turn.trace, parsed as AgentEvent],
              }))
            }

            // Final reply from ReAct or chitchat
            if (parsed.type === 'reply' && parsed.done) {
              const execResults = parsed.execution_results || []
              updateConversation(turnId, (turn) => ({
                ...turn,
                result: {
                  reply: parsed.content || streamedReply || '',
                  execution_results: execResults.length ? execResults : undefined,
                },
                statusText: undefined,
              }))
              onChatResult?.(text, { reply: parsed.content || streamedReply || '' })
            }

            // error
            if (parsed.type === 'error' && parsed.done) {
              updateConversation(turnId, (turn) => ({
                ...turn,
                result: { reply: parsed.content || '发生错误' },
              }))
            }
          } catch {
            /* ignore malformed SSE line */
          }
        }
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '连接失败，请检查后端是否运行'
      updateConversation(turnId, (turn) => ({ ...turn, result: { reply: errorMessage } }))
    } finally {
      setSending(false)
    }
  }

  return (
    <aside className="w-[400px] min-w-[400px] border-l border-slate-200/80 bg-white flex flex-col shadow-[-1px_0_0_#e2e8f0]">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2">
        <div className="flex items-center justify-center w-6 h-6 rounded-lg bg-violet-600">
          <Brain className="w-3.5 h-3.5 text-white" />
        </div>
        <h2 className="text-sm font-semibold text-slate-700">Anima</h2>
        <span className="ml-auto text-[10px] text-slate-400 font-medium">AI 助手</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {conversation.length === 0 ? (
          <div className="p-8 text-center mt-6">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-violet-50">
              <Sparkles className="w-6 h-6 text-violet-400" />
            </div>
            <p className="text-sm font-medium text-slate-600">和 Anima 说话，控制你的设备</p>
            <p className="mt-1.5 text-xs text-slate-400 leading-relaxed">例如：打开客厅的灯<br />把卧室空调调到 26 度</p>
          </div>
        ) : (
          <div className="py-4 space-y-1">
            {conversation.map((turn) => (
              <ConversationCard key={turn.id} turn={turn} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="border-t border-slate-100 bg-white p-3.5">
        <div className="flex items-end gap-2.5">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void handleSend()
              }
            }}
            rows={2}
            placeholder="说点什么..."
            className="flex-1 resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition-all focus:border-violet-500 focus:ring-2 focus:ring-violet-500/15 focus:bg-white placeholder:text-slate-400"
          />
          <button
            onClick={() => void handleSend()}
            disabled={sending || !message.trim()}
            className="inline-flex h-[52px] w-[52px] items-center justify-center rounded-2xl bg-violet-600 text-white transition-all hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-40 shadow-sm hover:shadow-md"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </aside>
  )
}

function AgentTrace({ trace }: { trace: AgentEvent[] }) {
  const [open, setOpen] = useState(false)
  if (!trace.length) return null
  return (
    <div className="mb-2 ml-1">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-slate-600 transition-colors mb-1"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <Wrench className="w-3 h-3 text-amber-400" />
        <span>{trace.length} 步工具调用</span>
      </button>
      {open && (
        <div className="space-y-1 pl-2 border-l border-slate-100">
          {trace.map((event, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-slate-500">
              {event.type === 'action' ? (
                <>
                  <Wrench className="mt-0.5 h-3 w-3 shrink-0 text-amber-400" />
                  <span>
                    <span className="font-medium text-amber-600">{event.tool}</span>
                    {event.args && Object.keys(event.args).length > 0 && (
                      <span className="ml-1 text-slate-400">({JSON.stringify(event.args)})</span>
                    )}
                  </span>
                </>
              ) : event.type === 'observation' ? (
                <>
                  <span className="mt-0.5 h-3 w-3 shrink-0 text-center text-[10px] text-emerald-500">↩</span>
                  <span className="text-slate-400 line-clamp-2">{event.result}</span>
                </>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ConversationCard({ turn }: { turn: ConversationTurn }) {
  const [replyOpen, setReplyOpen] = useState(true)
  const execResults = turn.result.execution_results || []
  const hasExecution = execResults.length > 0
  const hasTrace = turn.trace.length > 0
  const hasReply = Boolean(turn.result.reply)
  const hasStatus = Boolean(turn.statusText)

  // Proactive brain action — no user bubble, special header
  if (turn.isProactive) {
    return (
      <div className="px-4 py-2">
        <div className="flex mb-2">
          <div className="max-w-[92%] rounded-[18px] rounded-tl-sm border border-emerald-200/80 bg-emerald-50/60 shadow-sm overflow-hidden">
            <div className="flex items-center gap-2 px-4 pt-3 pb-2 text-[10px] uppercase tracking-widest text-emerald-600 font-semibold">
              <Sparkles className="h-3 w-3" />
              <span>Anima 自动执行</span>
              <span className="ml-auto text-emerald-400 normal-case font-normal">{formatTime(turn.timestamp)}</span>
            </div>
            <div className="px-4 pb-3">
              <MarkdownMessage content={turn.result.reply} />
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="px-4 py-2">
      {/* User message */}
      <div className="flex justify-end mb-2">
        <div className="max-w-[85%] rounded-[18px] rounded-tr-sm bg-violet-600 px-4 py-3 text-sm leading-6 text-white shadow-sm">
          <div className="mb-1 text-[10px] uppercase tracking-widest text-violet-300 flex items-center gap-1">
            <Clock className="inline w-2.5 h-2.5" />{formatTime(turn.timestamp)}
          </div>
          {turn.userMessage}
        </div>
      </div>

      {/* Status indicator — real-time progress */}
      {hasStatus && (
        <div className="flex mb-2">
          <div className="rounded-[18px] rounded-tl-sm border border-amber-100 bg-amber-50/60 px-4 py-2.5 flex items-center gap-2">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-500" />
            <span className="text-xs text-amber-600 font-medium">{turn.statusText}</span>
          </div>
        </div>
      )}

      {/* Agent trace — collapsible */}
      {hasTrace && <AgentTrace trace={turn.trace} />}

      {/* Assistant reply — collapsible */}
      {hasReply ? (
        <div className="flex mb-2">
          <div className="max-w-[92%] rounded-[18px] rounded-tl-sm border border-slate-200/80 bg-white shadow-sm overflow-hidden">
            <button
              onClick={() => setReplyOpen(o => !o)}
              className="w-full flex items-center gap-2 px-4 pt-3 pb-2 text-[10px] uppercase tracking-widest text-violet-500 font-semibold hover:text-violet-700 transition-colors"
            >
              {replyOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              <Sparkles className="h-3 w-3" />
              <span>Anima</span>
            </button>
            {replyOpen && (
              <div className="px-4 pb-3">
                <MarkdownMessage content={turn.result.reply} />
                {turn.qrImage ? (
                  <div className="mt-3 rounded-xl border border-slate-100 bg-slate-50 p-3">
                    <img src={`data:image/png;base64,${turn.qrImage}`} alt="米家扫码登录" className="mx-auto h-40 w-40 rounded-lg border border-slate-200" />
                    <p className="mt-2 flex items-center justify-center gap-2 text-sm text-violet-600">
                      <Loader2 className={`h-4 w-4 ${turn.qrPolling ? 'animate-spin' : ''}`} />
                      请打开米家 App 扫码
                    </p>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </div>
      ) : turn.result.reply === '' && !hasExecution && !hasTrace && !hasStatus ? (
        <div className="flex mb-2">
          <div className="rounded-[18px] rounded-tl-sm border border-slate-100 bg-slate-50 px-4 py-3">
            <Loader2 className="h-4 w-4 animate-spin text-slate-300" />
          </div>
        </div>
      ) : turn.result.reply === '' && hasTrace && !hasStatus ? (
        <div className="flex mb-2">
          <div className="rounded-[18px] rounded-tl-sm border border-violet-100 bg-violet-50/60 px-4 py-3 flex items-center gap-2">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-400" />
            <span className="text-xs text-violet-500 font-medium">思考中...</span>
          </div>
        </div>
      ) : null}

      {/* Execution result */}
      {hasExecution && <ExecutionSummaryCard items={execResults} />}
    </div>
  )
}
