import { Bot, Cpu, Loader2, MessageSquareText, Plus, RefreshCw, Sparkles, Wrench, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { api, useSkills, type SkillInventoryItem } from '../hooks/useApi'

interface SkillsPanelProps {
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

function statusLabel(skill: SkillInventoryItem) {
  if (skill.has_decide_prompt && skill.device_types.length > 0) {
    return { label: 'Executable', className: 'bg-emerald-50 text-emerald-700 ring-emerald-200' }
  }
  if (skill.has_chat_prompt) {
    return { label: 'Chat-only', className: 'bg-amber-50 text-amber-700 ring-amber-200' }
  }
  return { label: 'Incomplete', className: 'bg-slate-100 text-slate-600 ring-slate-200' }
}

function SkillCard({ skill }: { skill: SkillInventoryItem }) {
  const status = statusLabel(skill)

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold text-slate-800">{skill.name}</h4>
            <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ${status.className}`}>
              {status.label}
            </span>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-600">{skill.description || 'No description provided.'}</p>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${skill.scope === 'system' ? 'bg-violet-100 text-violet-700' : 'bg-sky-100 text-sky-700'}`}>
          {skill.scope === 'system' ? 'System' : 'Custom'}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {skill.device_types.length ? skill.device_types.map((deviceType) => (
          <span key={deviceType} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600">
            {deviceType}
          </span>
        )) : (
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-500">no device types</span>
        )}
      </div>

      <div className="mt-4 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
        <div>Folder: <span className="font-medium text-slate-700">{skill.folder_name}</span></div>
        <div>Version: <span className="font-medium text-slate-700">{skill.version}</span></div>
        <div className="flex items-center gap-1.5">
          <Wrench className="h-3.5 w-3.5" />
          <span>{skill.has_actions ? 'has actions module' : 'no actions module'}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <MessageSquareText className="h-3.5 w-3.5" />
          <span>{skill.has_chat_prompt ? 'has chat prompt' : 'no chat prompt'}</span>
        </div>
      </div>
    </div>
  )
}

export default function SkillsPanel({ open, onClose }: SkillsPanelProps) {
  const { skills, loading, refresh } = useSkills(open ? 10000 : 30000)
  const [query, setQuery] = useState('')
  const [draft, setDraft] = useState('')
  const [createReply, setCreateReply] = useState('')
  const [createError, setCreateError] = useState('')
  const [creating, setCreating] = useState(false)

  const normalizedQuery = query.trim().toLowerCase()
  const filtered = useMemo(() => {
    const matches = (skill: SkillInventoryItem) => {
      if (!normalizedQuery) return true
      const haystack = [
        skill.name,
        skill.description,
        skill.folder_name,
        ...skill.device_types,
      ].join(' ').toLowerCase()
      return haystack.includes(normalizedQuery)
    }

    return {
      system: (skills?.system_skills || []).filter(matches),
      custom: (skills?.custom_skills || []).filter(matches),
    }
  }, [normalizedQuery, skills])

  if (!open) return null

  const systemCount = skills?.system_skills.length ?? 0
  const customCount = skills?.custom_skills.length ?? 0

  const handleCreateSkill = async () => {
    const text = draft.trim()
    if (!text || creating) return

    setCreating(true)
    setCreateError('')
    try {
      const result = await api.chat(text)
      setCreateReply(result.reply || '技能请求已提交')
      setDraft('')
      await refresh()
    } catch (error) {
      const message = error instanceof Error ? error.message : '新增技能失败'
      setCreateError(message)
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/35 backdrop-blur-[2px]">
      <div className="flex h-full w-full max-w-4xl flex-col overflow-hidden bg-[#f6f4ee] shadow-2xl ring-1 ring-black/5">
        <div className="flex items-center justify-between border-b border-black/10 bg-[#0f172a] px-6 py-4 text-white">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-sky-300/15 p-2 text-sky-200">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Skills Center</h2>
              <p className="text-sm text-slate-300">严格展示系统技能与真实落盘的自定义技能</p>
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

        <div className="border-b border-black/10 bg-white/70 px-6 py-4">
          <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
            <div className="rounded-[28px] border border-slate-200 bg-white/90 p-4 shadow-sm">
              <div className="flex items-center gap-2">
                <div className="rounded-xl bg-sky-100 p-2 text-sky-700">
                  <Plus className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-800">新增自定义技能</h3>
                  <p className="text-xs text-slate-500">输入技能描述后创建；如果需要补充信息，直接在这里继续回复。</p>
                </div>
              </div>

              <div className="mt-4 flex gap-3">
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder="例如：新增一个技能，工作日早上 7:30 通过小米音箱提醒我起床，法定节假日不提醒。"
                  rows={4}
                  className="min-h-[104px] flex-1 resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700 outline-none transition focus:border-sky-400"
                />
                <button
                  onClick={handleCreateSkill}
                  disabled={creating || !draft.trim()}
                  className="inline-flex min-w-[128px] items-center justify-center gap-2 self-stretch rounded-2xl bg-sky-600 px-4 py-3 text-sm font-medium text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                  <span>{creating ? '创建中' : '新增技能'}</span>
                </button>
              </div>

              {createReply ? (
                <div className="mt-3 rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm leading-6 text-emerald-800">
                  <span className="font-medium">Anima: </span>
                  {createReply}
                </div>
              ) : null}

              {createError ? (
                <div className="mt-3 rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-700">
                  {createError}
                </div>
              ) : null}
            </div>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
              <input
                type="text"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索技能名、描述、目录名或设备类型"
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-sky-400"
              />
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-2xl bg-slate-900 px-4 py-3 text-white">
                  <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-slate-400">
                    <Cpu className="h-3.5 w-3.5" />
                    <span>System</span>
                  </div>
                  <div className="mt-2 text-2xl font-semibold">{systemCount}</div>
                </div>
                <div className="rounded-2xl bg-sky-600 px-4 py-3 text-white">
                  <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-sky-100">
                    <Bot className="h-3.5 w-3.5" />
                    <span>Custom</span>
                  </div>
                  <div className="mt-2 text-2xl font-semibold">{customCount}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid flex-1 gap-0 overflow-hidden md:grid-cols-2">
          <div className="overflow-y-auto border-r border-black/10 bg-[#f8f6f0] px-6 py-5">
            <SectionTitle title="System Skills" detail={`${filtered.system.length} visible`} />
            <div className="mt-4 space-y-3">
              {filtered.system.length ? filtered.system.map((skill) => (
                <SkillCard key={`system-${skill.folder_name}`} skill={skill} />
              )) : (
                <p className="text-sm text-slate-500">{loading ? '正在加载系统技能...' : '没有匹配到系统技能'}</p>
              )}
            </div>
          </div>

          <div className="overflow-y-auto bg-[#f1ede4] px-6 py-5">
            <SectionTitle title="Custom Skills" detail={`${filtered.custom.length} visible`} />
            <div className="mt-4 space-y-3">
              {filtered.custom.length ? filtered.custom.map((skill) => (
                <SkillCard key={`custom-${skill.folder_name}`} skill={skill} />
              )) : (
                <p className="text-sm text-slate-500">{loading ? '正在加载自定义技能...' : '当前没有真实落盘的自定义技能'}</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
