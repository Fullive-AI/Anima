import { BrainCircuit, Clock3, Database, RefreshCw, ShieldCheck, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useMemoryDebug } from '../hooks/useApi'

interface MemoryPanelProps {
  open: boolean
  onClose: () => void
}

function SectionTitle({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <h3 className="text-sm font-medium uppercase tracking-wider text-slate-500">{title}</h3>
      {detail ? <span className="text-xs text-slate-400">{detail}</span> : null}
    </div>
  )
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*.*?\*\*)/g)
  return parts.filter(Boolean).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={index} className="font-semibold text-slate-900">{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return <code key={index} className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-700">{part.slice(1, -1)}</code>
    }
    return <span key={index}>{part}</span>
  })
}

function MarkdownBlock({ content, emptyText = 'No content.' }: { content?: string; emptyText?: string }) {
  const text = (content || '').trim()
  if (!text) {
    return <p className="text-sm text-slate-400">{emptyText}</p>
  }

  const lines = text.split('\n').map((line) => line.trimEnd())
  const blocks: ReactNode[] = []
  let listItems: string[] = []

  const flushList = (key: string) => {
    if (!listItems.length) return
    blocks.push(
      <ul key={key} className="ml-5 list-disc space-y-1 text-sm leading-6 text-slate-700">
        {listItems.map((item, index) => (
          <li key={`${key}-${index}`}>{renderInlineMarkdown(item)}</li>
        ))}
      </ul>,
    )
    listItems = []
  }

  lines.forEach((rawLine, index) => {
    const line = rawLine.trim()
    if (!line) {
      flushList(`list-${index}`)
      return
    }

    const bulletMatch = line.match(/^[-*•]\s+(.*)$/)
    const orderedMatch = line.match(/^\d+\.\s+(.*)$/)
    if (bulletMatch || orderedMatch) {
      listItems.push((bulletMatch || orderedMatch)?.[1] || '')
      return
    }

    flushList(`list-${index}`)

    if (line.startsWith('### ')) {
      blocks.push(<h3 key={`h3-${index}`} className="text-sm font-semibold text-slate-900">{renderInlineMarkdown(line.slice(4))}</h3>)
      return
    }
    if (line.startsWith('## ')) {
      blocks.push(<h2 key={`h2-${index}`} className="text-base font-semibold text-slate-900">{renderInlineMarkdown(line.slice(3))}</h2>)
      return
    }
    if (line.startsWith('# ')) {
      blocks.push(<h1 key={`h1-${index}`} className="text-lg font-semibold text-slate-900">{renderInlineMarkdown(line.slice(2))}</h1>)
      return
    }

    blocks.push(<p key={`p-${index}`} className="text-sm leading-6 text-slate-700">{renderInlineMarkdown(line)}</p>)
  })

  flushList('list-final')
  return <div className="space-y-2">{blocks}</div>
}

function Tag({ children, tone = 'slate' }: { children: ReactNode; tone?: 'slate' | 'amber' | 'emerald' | 'violet' }) {
  const classes = {
    slate: 'bg-slate-100 text-slate-600 ring-slate-200',
    amber: 'bg-amber-100 text-amber-700 ring-amber-200',
    emerald: 'bg-emerald-100 text-emerald-700 ring-emerald-200',
    violet: 'bg-violet-100 text-violet-700 ring-violet-200',
  }
  return <span className={`rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${classes[tone]}`}>{children}</span>
}

function MarkdownListCard({ title, items, emptyText }: { title: string; items: string[]; emptyText: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{title}</div>
      <div className="mt-2">
        <MarkdownBlock content={items.map((item) => `- ${item}`).join('\n')} emptyText={emptyText} />
      </div>
    </div>
  )
}

export default function MemoryPanel({ open, onClose }: MemoryPanelProps) {
  const { memory, loading, refresh } = useMemoryDebug(open ? 5000 : 15000)

  if (!open) return null

  const learnedProfiles = memory ? Object.entries(memory.learned_profiles) : []
  const topicMemories = memory ? Object.values(memory.extracted_memories) : []

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/30 px-6 py-8">
      <div className="flex h-full max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-slate-50 shadow-xl ring-1 ring-slate-200">
        <div className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-violet-100 p-2 text-violet-600">
              <BrainCircuit className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-800">记忆调试</h2>
              <p className="text-sm text-slate-400">偏好、长期记忆和学习状态的实时视图</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={refresh}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-50 cursor-pointer"
            >
              <RefreshCw className="h-4 w-4" />
              刷新
            </button>
            <button
              onClick={onClose}
              className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 cursor-pointer"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="grid flex-1 gap-0 overflow-hidden md:grid-cols-[1.15fr_0.85fr]">
          <div className="overflow-y-auto border-r border-slate-200 bg-slate-50 px-6 py-5">
            <div className="space-y-6">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <SectionTitle
                  title="提取状态"
                  detail={memory?.extraction_state.last_extracted_at ? new Date(memory.extraction_state.last_extracted_at).toLocaleString() : '尚未提取'}
                />
                {memory ? (
                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                      <div className="text-xs uppercase tracking-wide text-slate-400">History Cursor</div>
                      <div className="mt-2 text-2xl font-semibold text-slate-800">{memory.extraction_state.history_cursor}</div>
                    </div>
                    <div className="rounded-xl border border-violet-100 bg-violet-50 px-4 py-3">
                      <div className="text-xs uppercase tracking-wide text-violet-400">Last Batch</div>
                      <div className="mt-2 text-2xl font-semibold text-violet-700">{memory.extraction_state.last_batch_size ?? 0}</div>
                    </div>
                    <div className="rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3">
                      <div className="text-xs uppercase tracking-wide text-emerald-500">Topic Memories</div>
                      <div className="mt-2 text-2xl font-semibold text-emerald-700">{topicMemories.length}</div>
                    </div>
                  </div>
                ) : (
                  <p className="mt-4 text-sm text-slate-500">{loading ? '正在加载...' : '暂无数据'}</p>
                )}
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <SectionTitle title="用户偏好" detail="preferences.md" />
                <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <MarkdownBlock content={memory?.preferences} emptyText={loading ? 'Loading preferences...' : 'No preferences yet.'} />
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <SectionTitle title="设备学习档案" detail={`${learnedProfiles.length} profiles`} />
                <div className="mt-4 space-y-3">
                  {learnedProfiles.length === 0 ? (
                    <p className="text-sm text-slate-500">{loading ? '正在加载...' : '还没有 learned profiles'}</p>
                  ) : (
                    learnedProfiles.map(([deviceType, profile]) => (
                      <div key={deviceType} className="rounded-xl border border-slate-200 bg-white p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-semibold text-slate-800">{deviceType}</div>
                            <div className="mt-2">
                              <MarkdownBlock content={profile.confidence_notes} emptyText="No confidence notes yet." />
                            </div>
                          </div>
                          <Tag>{(profile.metadata?.history_samples as number | undefined) ?? 0} history samples</Tag>
                        </div>
                        <div className="mt-4 grid gap-3 md:grid-cols-2">
                          <MarkdownListCard title="Stable Preferences" items={profile.stable_preferences} emptyText="No stable preferences yet." />
                          <MarkdownListCard title="Time Patterns" items={profile.time_based_patterns} emptyText="No time patterns yet." />
                          <MarkdownListCard title="Seasonal Patterns" items={profile.seasonal_patterns} emptyText="No seasonal patterns yet." />
                          <MarkdownListCard title="Weak Signals" items={profile.weak_signals} emptyText="No weak signals yet." />
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="overflow-y-auto bg-slate-50 px-6 py-5">
            <div className="space-y-6">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <SectionTitle title="记忆目录" detail={`${memory?.memory_manifest.length ?? 0} topics`} />
                <div className="mt-4 space-y-2">
                  {memory?.memory_manifest.length ? memory.memory_manifest.map((item) => (
                    <div key={item.topic} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium text-slate-800">{item.title}</div>
                          <div className="mt-2"><Tag tone="violet">{item.category}</Tag></div>
                        </div>
                        <Database className="mt-0.5 h-4 w-4 text-slate-400" />
                      </div>
                      <div className="mt-3"><MarkdownBlock content={item.summary} /></div>
                    </div>
                  )) : <p className="text-sm text-slate-500">{loading ? '正在加载...' : '还没有 manifest topics'}</p>}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <SectionTitle title="长期记忆" detail={`${topicMemories.length} stored`} />
                <div className="mt-4 space-y-3">
                  {topicMemories.length === 0 ? (
                    <p className="text-sm text-slate-500">{loading ? '正在加载...' : '还没有长期记忆 topic'}</p>
                  ) : (
                    topicMemories.map((memoryItem) => (
                      <div key={memoryItem.topic} className="rounded-xl border border-slate-200 bg-white p-4 transition-colors hover:bg-slate-50/70">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-semibold text-slate-900">{memoryItem.title}</div>
                            <div className="mt-2 flex flex-wrap gap-2">
                              <Tag tone="violet">{memoryItem.category}</Tag>
                              <Tag tone={memoryItem.status === 'confirmed' ? 'emerald' : memoryItem.status === 'candidate' ? 'amber' : 'slate'}>
                                {memoryItem.status}
                              </Tag>
                              <Tag tone={memoryItem.confidence === 'high' ? 'emerald' : memoryItem.confidence === 'medium' ? 'amber' : 'slate'}>
                                {memoryItem.confidence}
                              </Tag>
                              <Tag>{memoryItem.claim_type}</Tag>
                              <Tag>{memoryItem.evidence_count} evidence</Tag>
                            </div>
                          </div>
                          <ShieldCheck className="h-4 w-4 text-emerald-500" />
                        </div>
                        <div className="mt-3"><MarkdownBlock content={memoryItem.summary} /></div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {memoryItem.device_types.map((deviceType) => (
                            <Tag key={deviceType}>{deviceType}</Tag>
                          ))}
                          {memoryItem.scenes.map((scene) => (
                            <Tag key={scene} tone="amber">{scene}</Tag>
                          ))}
                        </div>
                        {memoryItem.details.length ? (
                          <div className="mt-3 rounded-xl bg-slate-50 p-3">
                            <MarkdownBlock content={memoryItem.details.map((detail) => `- ${detail}`).join('\n')} />
                          </div>
                        ) : null}
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <SectionTitle title="最近历史" detail={`${memory?.recent_history.length ?? 0} entries`} />
                <div className="mt-4 space-y-2">
                  {memory?.recent_history.length ? memory.recent_history.map((entry, index) => (
                    <div key={`${entry.timestamp ?? 'row'}-${index}`} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3">
                      <div className="flex items-center gap-2 text-xs text-slate-500">
                        <Clock3 className="h-3.5 w-3.5" />
                        <span>{entry.timestamp ? new Date(entry.timestamp).toLocaleString() : 'No timestamp'}</span>
                      </div>
                      <div className="mt-2 text-sm font-medium text-slate-800">{entry.action || entry.task_kind || 'unknown action'}</div>
                      <p className="mt-1 text-sm text-slate-600">{entry.reason || entry.goal || entry.message || 'No explanation recorded.'}</p>
                    </div>
                  )) : <p className="text-sm text-slate-500">{loading ? '正在加载...' : '还没有最近历史'}</p>}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
