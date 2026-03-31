import { Brain, Clock, GitBranch, MessageSquareMore, RefreshCw, Sparkles, Wrench } from 'lucide-react'
import type { ChatExecutionResult, ChatResponse, ChatTaskPlanItem, ChatTaskResult, Decision } from '../hooks/useApi'

interface DecisionLogProps {
  decisions: Decision[]
  liveTrace?: LiveTrace | null
}

export interface LiveTrace {
  timestamp: string
  message: string
  result: ChatResponse
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

export default function DecisionLog({ decisions, liveTrace }: DecisionLogProps) {
  const recent = [...decisions].reverse().slice(0, 50)

  return (
    <aside className="w-72 min-w-[288px] bg-white border-l border-slate-200 flex flex-col">
      <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2">
        <Brain className="w-4 h-4 text-violet-500" />
        <h2 className="text-sm font-medium text-slate-500 uppercase tracking-wider">AI 决策流</h2>
      </div>

      <div className="flex-1 overflow-y-auto">
        {liveTrace && (
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
              <p className="mt-1 text-xs text-violet-700">{liveTrace.result.reply}</p>
            </div>
            <div className="space-y-2">
              {(liveTrace.result.task_plan_items || []).map((task, index) => (
                <TaskPlanCard key={`${liveTrace.timestamp}-plan-${index}`} task={task} />
              ))}
              {(liveTrace.result.task_results || []).map((task, index) => (
                <TaskResultCard key={`${liveTrace.timestamp}-${index}`} task={task} />
              ))}
              {(liveTrace.result.execution_results || []).map((item, index) => (
                <ExecutionResultCard key={`${liveTrace.timestamp}-exec-${index}`} item={item} />
              ))}
            </div>
          </div>
        )}

        {recent.length === 0 ? (
          <div className="p-4 text-sm text-slate-400 text-center">
            <p>暂无决策记录</p>
            <p className="mt-1 text-xs">AI 做出决策后会实时显示在这里</p>
          </div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {recent.map((d, i) => (
              <li key={i} className="px-4 py-3 hover:bg-slate-50 transition-colors">
                <div className="flex items-center gap-2 mb-1">
                  <Clock className="w-3 h-3 text-slate-300" />
                  <span className="text-xs text-slate-400 font-mono">{formatTime(d.timestamp)}</span>
                </div>
                <p className="text-sm text-slate-700">
                  <span className="text-violet-600 font-medium">{formatDecisionAction(d.action)}</span>
                  {d.device_id && <span className="text-slate-400"> → {d.device_id}</span>}
                </p>
                {d.reason && (
                  <p className="text-xs text-slate-400 mt-1">{d.reason}</p>
                )}
                {d.action?.startsWith('plan.') && 'goal' in d && typeof d.goal === 'string' && d.goal && (
                  <p className="mt-1 text-xs text-violet-600">{d.goal}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}

function TaskPlanCard({ task }: { task: ChatTaskPlanItem }) {
  return (
    <div className="rounded-lg border border-violet-100 bg-violet-50 px-3 py-2">
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
      {detail && <p className="mt-1 text-xs text-slate-500">{detail}</p>}
    </div>
  )
}

function ExecutionResultCard({ item }: { item: ChatExecutionResult }) {
  return (
    <div className="rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2">
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
