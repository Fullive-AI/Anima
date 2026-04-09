import { BrainCircuit, Clock3, Database, RefreshCw, ShieldCheck, X } from 'lucide-react'
import { useMemoryDebug } from '../hooks/useApi'

interface MemoryPanelProps {
  open: boolean
  onClose: () => void
}

function SectionTitle({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="flex items-end justify-between gap-3">
      <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">{title}</h3>
      {detail ? <span className="text-xs text-slate-400">{detail}</span> : null}
    </div>
  )
}

export default function MemoryPanel({ open, onClose }: MemoryPanelProps) {
  const { memory, loading, refresh } = useMemoryDebug(open ? 5000 : 15000)

  if (!open) return null

  const learnedProfiles = memory ? Object.entries(memory.learned_profiles) : []
  const topicMemories = memory ? Object.values(memory.extracted_memories) : []

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/35 backdrop-blur-[2px]">
      <div className="flex h-full w-full max-w-3xl flex-col overflow-hidden bg-[#f3efe6] shadow-2xl ring-1 ring-black/5">
        <div className="flex items-center justify-between border-b border-black/10 bg-[#1f2937] px-6 py-4 text-white">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-amber-300/20 p-2 text-amber-200">
              <BrainCircuit className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Memory Debugger</h2>
              <p className="text-sm text-slate-300">偏好、长期记忆和学习状态的实时视图</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={refresh}
              className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/10 px-3 py-2 text-sm text-white transition hover:bg-white/15 cursor-pointer"
            >
              <RefreshCw className="h-4 w-4" />
              刷新
            </button>
            <button
              onClick={onClose}
              className="rounded-xl p-2 text-slate-300 transition hover:bg-white/10 hover:text-white cursor-pointer"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="grid flex-1 gap-0 overflow-hidden md:grid-cols-[1.15fr_0.85fr]">
          <div className="overflow-y-auto border-r border-black/10 bg-[#f8f3e8] px-6 py-5">
            <div className="space-y-6">
              <div className="rounded-2xl border border-amber-950/10 bg-white/70 p-4 shadow-sm">
                <SectionTitle
                  title="Extraction State"
                  detail={memory?.extraction_state.last_extracted_at ? new Date(memory.extraction_state.last_extracted_at).toLocaleString() : '尚未提取'}
                />
                {memory ? (
                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    <div className="rounded-2xl bg-slate-900 px-4 py-3 text-white">
                      <div className="text-xs uppercase tracking-wide text-slate-400">History Cursor</div>
                      <div className="mt-2 text-2xl font-semibold">{memory.extraction_state.history_cursor}</div>
                    </div>
                    <div className="rounded-2xl bg-[#8b5cf6] px-4 py-3 text-white">
                      <div className="text-xs uppercase tracking-wide text-violet-200">Last Batch</div>
                      <div className="mt-2 text-2xl font-semibold">{memory.extraction_state.last_batch_size ?? 0}</div>
                    </div>
                    <div className="rounded-2xl bg-[#c2410c] px-4 py-3 text-white">
                      <div className="text-xs uppercase tracking-wide text-orange-100">Topic Memories</div>
                      <div className="mt-2 text-2xl font-semibold">{topicMemories.length}</div>
                    </div>
                  </div>
                ) : (
                  <p className="mt-4 text-sm text-slate-500">{loading ? '正在加载...' : '暂无数据'}</p>
                )}
              </div>

              <div className="rounded-2xl border border-black/10 bg-white/70 p-4 shadow-sm">
                <SectionTitle title="Preferences.md" />
                <pre className="mt-4 overflow-x-auto rounded-2xl bg-[#111827] p-4 text-xs leading-6 text-emerald-200">
                  {memory?.preferences || (loading ? 'Loading preferences...' : 'No preferences yet.')}
                </pre>
              </div>

              <div className="rounded-2xl border border-black/10 bg-white/70 p-4 shadow-sm">
                <SectionTitle title="Device Learned Profiles" detail={`${learnedProfiles.length} profiles`} />
                <div className="mt-4 space-y-3">
                  {learnedProfiles.length === 0 ? (
                    <p className="text-sm text-slate-500">{loading ? '正在加载...' : '还没有 learned profiles'}</p>
                  ) : (
                    learnedProfiles.map(([deviceType, profile]) => (
                      <div key={deviceType} className="rounded-2xl border border-slate-200 bg-white p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-semibold text-slate-800">{deviceType}</div>
                            <div className="mt-1 text-xs text-slate-500">{profile.confidence_notes || 'No confidence notes yet.'}</div>
                          </div>
                          <div className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
                            {(profile.metadata?.history_samples as number | undefined) ?? 0} history samples
                          </div>
                        </div>
                        <div className="mt-4 grid gap-3 md:grid-cols-2">
                          <div className="rounded-xl bg-slate-50 p-3">
                            <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Stable Preferences</div>
                            <ul className="mt-2 space-y-2 text-sm text-slate-700">
                              {profile.stable_preferences.length ? profile.stable_preferences.map((item) => <li key={item}>• {item}</li>) : <li className="text-slate-400">No stable preferences yet.</li>}
                            </ul>
                          </div>
                          <div className="rounded-xl bg-slate-50 p-3">
                            <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Time Patterns</div>
                            <ul className="mt-2 space-y-2 text-sm text-slate-700">
                              {profile.time_based_patterns.length ? profile.time_based_patterns.map((item) => <li key={item}>• {item}</li>) : <li className="text-slate-400">No time patterns yet.</li>}
                            </ul>
                          </div>
                          <div className="rounded-xl bg-slate-50 p-3">
                            <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Seasonal Patterns</div>
                            <ul className="mt-2 space-y-2 text-sm text-slate-700">
                              {profile.seasonal_patterns.length ? profile.seasonal_patterns.map((item) => <li key={item}>• {item}</li>) : <li className="text-slate-400">No seasonal patterns yet.</li>}
                            </ul>
                          </div>
                          <div className="rounded-xl bg-slate-50 p-3">
                            <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Weak Signals</div>
                            <ul className="mt-2 space-y-2 text-sm text-slate-700">
                              {profile.weak_signals.length ? profile.weak_signals.map((item) => <li key={item}>• {item}</li>) : <li className="text-slate-400">No weak signals yet.</li>}
                            </ul>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="overflow-y-auto bg-[#efe8db] px-6 py-5">
            <div className="space-y-6">
              <div className="rounded-2xl border border-black/10 bg-white/80 p-4 shadow-sm">
                <SectionTitle title="Memory Manifest" detail={`${memory?.memory_manifest.length ?? 0} topics`} />
                <div className="mt-4 space-y-2">
                  {memory?.memory_manifest.length ? memory.memory_manifest.map((item) => (
                    <div key={item.topic} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium text-slate-800">{item.title}</div>
                          <div className="mt-1 text-xs uppercase tracking-wide text-slate-500">{item.category}</div>
                        </div>
                        <Database className="mt-0.5 h-4 w-4 text-slate-400" />
                      </div>
                      <p className="mt-2 text-sm text-slate-600">{item.summary}</p>
                    </div>
                  )) : <p className="text-sm text-slate-500">{loading ? '正在加载...' : '还没有 manifest topics'}</p>}
                </div>
              </div>

              <div className="rounded-2xl border border-black/10 bg-white/80 p-4 shadow-sm">
                <SectionTitle title="Topic Memories" detail={`${topicMemories.length} stored`} />
                <div className="mt-4 space-y-3">
                  {topicMemories.length === 0 ? (
                    <p className="text-sm text-slate-500">{loading ? '正在加载...' : '还没有长期记忆 topic'}</p>
                  ) : (
                    topicMemories.map((memoryItem) => (
                      <div key={memoryItem.topic} className="rounded-2xl bg-[#111827] p-4 text-slate-100">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-semibold">{memoryItem.title}</div>
                            <div className="mt-1 text-xs uppercase tracking-wide text-slate-400">{memoryItem.category} · {memoryItem.confidence}</div>
                          </div>
                          <ShieldCheck className="h-4 w-4 text-emerald-300" />
                        </div>
                        <p className="mt-3 text-sm leading-6 text-slate-300">{memoryItem.summary}</p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {memoryItem.device_types.map((deviceType) => (
                            <span key={deviceType} className="rounded-full bg-white/10 px-2.5 py-1 text-xs text-slate-200">{deviceType}</span>
                          ))}
                        </div>
                        {memoryItem.details.length ? (
                          <ul className="mt-3 space-y-1 text-sm text-slate-300">
                            {memoryItem.details.map((detail) => <li key={detail}>• {detail}</li>)}
                          </ul>
                        ) : null}
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="rounded-2xl border border-black/10 bg-white/80 p-4 shadow-sm">
                <SectionTitle title="Recent History" detail={`${memory?.recent_history.length ?? 0} entries`} />
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
