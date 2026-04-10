import { useState, type ReactNode } from 'react'
import {
  Brain,
  Clock,
  GitBranch,
  Loader2,
  MessageSquare,
  MessageSquareMore,
  RefreshCw,
  Send,
  Sparkles,
  Wrench,
} from 'lucide-react'
import { api, type ChatExecutionResult, type ChatResponse, type ChatTaskPlanItem, type ChatTaskResult, type Decision } from '../hooks/useApi'

interface DecisionLogProps {
  decisions: Decision[]
  liveTrace?: LiveTrace | null
  onDevicesChanged: () => void
  onChatResult?: (message: string, result: ChatResponse) => void
}

export interface LiveTrace {
  timestamp: string
  message: string
  result: ChatResponse
}

interface ConversationTurn {
  id: string
  timestamp: string
  userMessage: string
  result: ChatResponse
  qrImage?: string
  qrPolling?: boolean
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

function renderInlineMarkdown(text: string): ReactNode[] {
  const parts = text.split(/(\*\*.*?\*\*)/g)
  return parts.filter(Boolean).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={index} className="font-semibold text-slate-800">{part.slice(2, -2)}</strong>
    }
    return <span key={index}>{part}</span>
  })
}

function MarkdownMessage({ content }: { content: string }) {
  const lines = content.split('\n').map((line) => line.trimEnd())
  const blocks: ReactNode[] = []
  let listItems: string[] = []

  const flushList = (key: string) => {
    if (!listItems.length) return
    blocks.push(
      <ol key={key} className="ml-5 list-decimal space-y-1 text-sm leading-6 text-slate-700">
        {listItems.map((item, index) => (
          <li key={`${key}-${index}`}>{renderInlineMarkdown(item)}</li>
        ))}
      </ol>,
    )
    listItems = []
  }

  lines.forEach((rawLine, index) => {
    const line = rawLine.trim()
    if (!line) {
      flushList(`list-${index}`)
      return
    }

    const orderedMatch = line.match(/^\d+\.\s+(.*)$/)
    if (orderedMatch) {
      listItems.push(orderedMatch[1])
      return
    }

    flushList(`list-${index}`)

    if (line.startsWith('### ')) {
      blocks.push(
        <h3 key={`h3-${index}`} className="text-sm font-semibold text-slate-900">
          {renderInlineMarkdown(line.slice(4))}
        </h3>,
      )
      return
    }

    if (line.startsWith('## ')) {
      blocks.push(
        <h2 key={`h2-${index}`} className="text-base font-semibold text-slate-900">
          {renderInlineMarkdown(line.slice(3))}
        </h2>,
      )
      return
    }

    if (line.startsWith('# ')) {
      blocks.push(
        <h1 key={`h1-${index}`} className="text-lg font-semibold text-slate-900">
          {renderInlineMarkdown(line.slice(2))}
        </h1>,
      )
      return
    }

    blocks.push(
      <p key={`p-${index}`} className="text-sm leading-6 text-slate-700">
        {renderInlineMarkdown(line)}
      </p>,
    )
  })

  flushList('list-final')

  return <div className="space-y-2">{blocks}</div>
}

export default function DecisionLog({ decisions, liveTrace, onDevicesChanged, onChatResult }: DecisionLogProps) {
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [conversation, setConversation] = useState<ConversationTurn[]>([])
  const recent = [...decisions]
    .filter((decision) => decision.action && !decision.action.startsWith('plan.'))
    .reverse()
    .slice(0, 30)

  const updateConversation = (id: string, updater: (turn: ConversationTurn) => ConversationTurn) => {
    setConversation((items) => items.map((item) => (item.id === id ? updater(item) : item)))
  }

  const handleSend = async () => {
    const text = message.trim()
    if (!text || sending) return

    setSending(true)
    try {
      const result = await api.chat(text)
      const turnId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const timestamp = new Date().toISOString()
      setConversation((items) => [
        ...items,
        {
          id: turnId,
          timestamp,
          userMessage: text,
          result,
          qrImage: result.qr_image_b64 || '',
          qrPolling: false,
        },
      ])
      onChatResult?.(text, result)
      setMessage('')

      if (result.refresh_devices) {
        onDevicesChanged()
      }

      if (result.status === 'qr_required' && result.qr_image_b64) {
        updateConversation(turnId, (turn) => ({ ...turn, qrPolling: true }))
        const country = result.country || 'cn'
        const pollInterval = window.setInterval(async () => {
          try {
            const response = await fetch('/api/settings/xiaomi/qr/poll', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ country }),
            })
            const pollResult = await response.json()
            if (pollResult.status === 'qr_pending') return

            window.clearInterval(pollInterval)
            updateConversation(turnId, (turn) => ({ ...turn, qrPolling: false, qrImage: '' }))

            if (pollResult.status === 'ok') {
              const reply = `连接成功：云端 ${pollResult.cloud_devices || 0} 台设备，更新 ${pollResult.updated || 0} 台，新增 ${pollResult.registered || 0} 台。`
              updateConversation(turnId, (turn) => ({
                ...turn,
                result: { ...turn.result, reply },
              }))
              onDevicesChanged()
              return
            }

            updateConversation(turnId, (turn) => ({
              ...turn,
              result: { ...turn.result, reply: pollResult.error || '扫码登录失败' },
            }))
          } catch {
            window.clearInterval(pollInterval)
            updateConversation(turnId, (turn) => ({
              ...turn,
              qrPolling: false,
              result: { ...turn.result, reply: '扫码状态轮询失败，请稍后重试' },
            }))
          }
        }, 2000)
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '连接失败，请检查后端是否运行'
      setConversation((items) => [
        ...items,
        {
          id: `${Date.now()}-error`,
          timestamp: new Date().toISOString(),
          userMessage: text,
          result: { reply: errorMessage },
        },
      ])
      setMessage('')
    } finally {
      setSending(false)
    }
  }

  return (
    <aside className="w-[420px] min-w-[420px] border-l border-slate-200 bg-white flex flex-col">
      <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2">
        <Brain className="w-4 h-4 text-violet-500" />
        <div>
          <h2 className="text-sm font-medium text-slate-500 uppercase tracking-wider">对话与 AI 决策流</h2>
          <p className="text-xs text-slate-400">连续展示用户消息、Anima 回复和每一步执行进度</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto bg-slate-50/70">
        {conversation.length === 0 && !liveTrace ? (
          <div className="p-5 text-sm text-slate-400">
            <p>右侧会持续展示完整对话和执行进度。</p>
            <p className="mt-1 text-xs">你发起的每一轮请求、Anima 的回复、plan 和 skill 执行都会留在这里。</p>
          </div>
        ) : null}

        {conversation.map((turn) => (
          <ConversationCard key={turn.id} turn={turn} />
        ))}

        {!conversation.length && liveTrace ? (
          <div className="border-b border-slate-200 bg-violet-50/50 p-4">
            <div className="mb-2 flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-violet-500" />
              <span className="text-xs font-medium uppercase tracking-wider text-violet-600">即时任务流</span>
            </div>
            <div className="mb-3 rounded-lg border border-violet-100 bg-white px-3 py-2">
              <div className="mb-1 flex items-center gap-2">
                <Clock className="h-3 w-3 text-slate-300" />
                <span className="text-xs font-mono text-slate-400">{formatTime(liveTrace.timestamp)}</span>
              </div>
              <p className="text-sm text-slate-700">{liveTrace.message}</p>
              <div className="mt-2 rounded-lg bg-violet-50 px-3 py-2 text-violet-700">
                <MarkdownMessage content={liveTrace.result.reply} />
              </div>
            </div>
          </div>
        ) : null}

        <div className="border-t border-slate-200 bg-white px-4 py-3">
          <div className="mb-2 flex items-center gap-2">
            <Clock className="h-3.5 w-3.5 text-slate-400" />
            <span className="text-xs font-medium uppercase tracking-wide text-slate-400">系统决策记录</span>
          </div>
          {recent.length === 0 ? (
            <p className="text-sm text-slate-400">暂无决策记录</p>
          ) : (
            <ul className="space-y-2">
              {recent.map((d, i) => (
                <li key={i} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                  <div className="flex items-center gap-2 mb-1">
                    <Clock className="w-3 h-3 text-slate-300" />
                    <span className="text-xs text-slate-400 font-mono">{formatTime(d.timestamp)}</span>
                  </div>
                  <p className="text-sm text-slate-700">
                    <span className="text-violet-600 font-medium">{formatDecisionAction(d.action)}</span>
                    {d.device_id && <span className="text-slate-400"> → {d.device_id}</span>}
                  </p>
                  {d.reason ? <p className="text-xs text-slate-400 mt-1">{d.reason}</p> : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="border-t border-slate-200 bg-white p-4">
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <div className="mb-2 flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-slate-400" />
              <span className="text-xs font-medium uppercase tracking-wide text-slate-400">对话输入</span>
            </div>
            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  void handleSend()
                }
              }}
              rows={3}
              placeholder="直接提需求、补充澄清信息，或让 Anima 新增一个 skill..."
              className="w-full resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-violet-400 focus:ring-1 focus:ring-violet-400"
            />
          </div>
          <button
            onClick={() => void handleSend()}
            disabled={sending || !message.trim()}
            className="inline-flex h-[52px] items-center gap-2 rounded-2xl bg-violet-500 px-4 text-sm font-medium text-white transition hover:bg-violet-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            <span>{sending ? '发送中' : '发送'}</span>
          </button>
        </div>
      </div>
    </aside>
  )
}

function ConversationCard({ turn }: { turn: ConversationTurn }) {
  return (
    <div className="border-b border-slate-200 bg-white px-4 py-4">
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-[20px] rounded-tr-md bg-slate-900 px-4 py-3 text-sm leading-6 text-white shadow-sm">
          <div className="mb-1 text-[11px] uppercase tracking-wide text-slate-400">You · {formatTime(turn.timestamp)}</div>
          {turn.userMessage}
        </div>
      </div>

      <div className="mt-3 space-y-2">
        <AssistantBubble timestamp={turn.timestamp}>
          <MarkdownMessage content={turn.result.reply} />
          {turn.qrImage ? (
            <div className="mt-3 rounded-xl border border-violet-100 bg-white p-3">
              <img
                src={`data:image/png;base64,${turn.qrImage}`}
                alt="米家扫码登录"
                className="mx-auto h-40 w-40 rounded-lg border border-slate-200"
              />
              <p className="mt-2 flex items-center justify-center gap-2 text-sm text-violet-600">
                <Loader2 className={`h-4 w-4 ${turn.qrPolling ? 'animate-spin' : ''}`} />
                请让客户打开米家 App 扫码
              </p>
            </div>
          ) : null}
        </AssistantBubble>

        {(turn.result.task_plan_items || []).filter((task) => task.kind !== 'reply').map((task, index) => (
          <AssistantBubble key={`${turn.id}-plan-${index}`} timestamp={turn.timestamp} accent="violet">
            <TaskPlanCard task={task} />
          </AssistantBubble>
        ))}

        {(turn.result.task_results || []).filter((task) => task.kind !== 'reply').map((task, index) => (
          <AssistantBubble key={`${turn.id}-task-${index}`} timestamp={turn.timestamp} accent="slate">
            <TaskResultCard task={task} />
          </AssistantBubble>
        ))}

        {(turn.result.execution_results || []).map((item, index) => (
          <AssistantBubble key={`${turn.id}-exec-${index}`} timestamp={turn.timestamp} accent="emerald">
            <ExecutionResultCard item={item} />
          </AssistantBubble>
        ))}
      </div>
    </div>
  )
}

function AssistantBubble({
  children,
  timestamp,
  accent = 'violet',
}: {
  children: ReactNode
  timestamp: string
  accent?: 'violet' | 'slate' | 'emerald'
}) {
  const shellClass =
    accent === 'emerald'
      ? 'border-emerald-100 bg-emerald-50'
      : accent === 'slate'
        ? 'border-slate-200 bg-slate-50'
        : 'border-violet-100 bg-violet-50'

  const textClass =
    accent === 'emerald'
      ? 'text-emerald-600'
      : accent === 'slate'
        ? 'text-slate-500'
        : 'text-violet-600'

  return (
    <div className="flex">
      <div className={`max-w-[92%] rounded-[22px] rounded-tl-md border px-4 py-3 text-sm leading-6 text-slate-700 shadow-sm ${shellClass}`}>
        <div className={`mb-1 flex items-center gap-2 text-[11px] uppercase tracking-wide ${textClass}`}>
          <Sparkles className="h-3.5 w-3.5" />
          <span>Anima · {formatTime(timestamp)}</span>
        </div>
        {children}
      </div>
    </div>
  )
}

function TaskPlanCard({ task }: { task: ChatTaskPlanItem }) {
  return (
    <div className="rounded-lg border border-violet-100 bg-white px-3 py-2">
      <div className="flex items-center gap-2">
        <GitBranch className="h-4 w-4 text-violet-600" />
        <span className="text-sm font-medium text-violet-700">
          计划任务: {getPlanLabel(task)}
        </span>
      </div>
      <p className="mt-1 text-xs text-violet-700">{getPlanDetail(task)}</p>
    </div>
  )
}

function TaskResultCard({ task }: { task: ChatTaskResult }) {
  const label = getTaskLabel(task)
  const detail = getTaskDetail(task)

  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
      <div className="flex items-center gap-2">
        {getTaskIcon(task.kind)}
        <span className="text-sm font-medium text-slate-700">{label}</span>
      </div>
      {detail ? <p className="mt-1 text-xs text-slate-500">{detail}</p> : null}
    </div>
  )
}

function ExecutionResultCard({ item }: { item: ChatExecutionResult }) {
  return (
    <div className="rounded-lg border border-emerald-100 bg-white px-3 py-2">
      <div className="flex items-center gap-2">
        <Wrench className="h-4 w-4 text-emerald-600" />
        <span className="text-sm font-medium text-emerald-700">
          执行 skill: {item.plan_item.skill_name}
        </span>
      </div>
      <p className="mt-1 text-xs text-emerald-700">{item.plan_item.goal || item.plan_item.reason}</p>
      {item.actions.map((action, index) => (
        <p key={`${action.device_id}-${action.action}-${index}`} className="mt-1 text-xs text-slate-600">
          {action.action} → {action.device_id}
        </p>
      ))}
    </div>
  )
}

function getTaskIcon(kind: string) {
  switch (kind) {
    case 'ask_user':
      return <MessageSquareMore className="h-4 w-4 text-amber-500" />
    case 'refresh_environment':
      return <RefreshCw className="h-4 w-4 text-sky-500" />
    case 'system_action':
    case 'execute_skill':
      return <Wrench className="h-4 w-4 text-violet-500" />
    default:
      return <Sparkles className="h-4 w-4 text-slate-400" />
  }
}

function getPlanLabel(task: ChatTaskPlanItem) {
  switch (task.kind) {
    case 'ask_user':
      return '向用户确认'
    case 'refresh_environment':
      return '刷新环境状态'
    case 'system_action':
      return `系统动作${task.system_action ? `: ${task.system_action}` : ''}`
    case 'execute_skill':
      return `执行 skill${task.skill_name ? `: ${task.skill_name}` : ''}`
    case 'reply':
      return '仅回复'
    default:
      return task.kind
  }
}

function getPlanDetail(task: ChatTaskPlanItem) {
  if (task.kind === 'ask_user') {
    return task.question || task.reason || '需要用户进一步确认'
  }
  if (task.kind === 'execute_skill') {
    return task.goal || task.reason || '执行设备任务'
  }
  if (task.kind === 'system_action') {
    return task.reason || task.system_action || '执行系统级动作'
  }
  if (task.kind === 'refresh_environment') {
    return task.reason || '先获取最新环境状态'
  }
  return task.reason || String(task.params?.reply || '规划阶段输出')
}

function getTaskLabel(task: ChatTaskResult) {
  switch (task.kind) {
    case 'ask_user':
      return '向用户确认'
    case 'refresh_environment':
      return '刷新环境状态'
    case 'system_action':
      return `系统动作${task.action ? `: ${task.action}` : ''}`
    case 'execute_skill':
      return '执行设备能力'
    case 'reply':
      return '仅回复'
    default:
      return task.kind
  }
}

function getTaskDetail(task: ChatTaskResult) {
  if (task.kind === 'ask_user') {
    return task.question || task.reply || task.reason || ''
  }
  if (task.kind === 'refresh_environment' && task.refresh_result) {
    return `刷新 ${task.refresh_result.refreshed} 台，失败 ${task.refresh_result.failed} 台`
  }
  if (task.kind === 'system_action') {
    if (typeof task.new_devices === 'number') {
      return `新增 ${task.new_devices} 台设备`
    }
    return task.reply || task.reason || ''
  }
  return task.reply || task.reason || ''
}

function formatDecisionAction(action?: string) {
  if (!action) return '(unknown)'
  if (action === 'plan.ask_user') return '计划: 向用户确认'
  if (action === 'plan.refresh_environment') return '计划: 刷新环境'
  if (action === 'plan.execute_skill') return '计划: 执行 skill'
  if (action === 'plan.system_action') return '计划: 系统动作'
  if (action === 'plan.reply') return '计划: 仅回复'
  return action
}
