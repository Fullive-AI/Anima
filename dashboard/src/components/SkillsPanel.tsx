import { Bot, Cpu, FilePenLine, Loader2, MessageSquareText, Plus, RefreshCw, Sparkles, Wrench, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api, useSkills, type CustomSkillDetail, type SkillInventoryItem, type UpdateCustomSkillRequest } from '../hooks/useApi'
import { useI18n } from '../i18n/useI18n'

type TFunction = (key: string, params?: Record<string, string | number>, fallback?: string) => string

interface SkillsPanelProps {
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

function statusLabel(skill: SkillInventoryItem, t: TFunction) {
  if (skill.has_decide_prompt && skill.device_types.length > 0) {
    return { label: t('skills.executable'), className: 'bg-emerald-50 text-emerald-700 ring-emerald-200' }
  }
  if (skill.has_chat_prompt) {
    return { label: t('skills.chatOnly'), className: 'bg-amber-50 text-amber-700 ring-amber-200' }
  }
  return { label: t('skills.incomplete'), className: 'bg-slate-100 text-slate-600 ring-slate-200' }
}

function SkillCard({
  skill,
  onEdit,
}: {
  skill: SkillInventoryItem
  onEdit?: (skill: SkillInventoryItem) => void
}) {
  const { t } = useI18n()
  const status = statusLabel(skill, t)

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition-colors hover:bg-slate-50/70">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold text-slate-800">{skill.name}</h4>
            <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ${status.className}`}>
              {status.label}
            </span>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-600">{skill.description || t('skills.noDescription')}</p>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${skill.scope === 'system' ? 'bg-slate-100 text-slate-600' : 'bg-violet-100 text-violet-700'}`}>
          {skill.scope === 'system' ? t('skills.system') : t('skills.custom')}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {skill.device_types.length ? skill.device_types.map((deviceType) => (
          <span key={deviceType} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600">
            {deviceType}
          </span>
        )) : (
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-500">{t('skills.noDeviceTypes')}</span>
        )}
      </div>

      <div className="mt-4 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
        <div>{t('skills.folder')}: <span className="font-medium text-slate-700">{skill.folder_name}</span></div>
        <div>{t('skills.version')}: <span className="font-medium text-slate-700">{skill.version}</span></div>
        <div className="flex items-center gap-1.5">
          <Wrench className="h-3.5 w-3.5" />
          <span>{skill.has_actions ? t('skills.hasActions') : t('skills.noActions')}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <MessageSquareText className="h-3.5 w-3.5" />
          <span>{skill.has_chat_prompt ? t('skills.hasChatPrompt') : t('skills.noChatPrompt')}</span>
        </div>
      </div>

      {skill.scope === 'custom' && onEdit ? (
        <div className="mt-4">
          <button
            onClick={() => onEdit(skill)}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-50 cursor-pointer"
          >
            <FilePenLine className="h-4 w-4" />
            {t('skills.editSkill')}
          </button>
        </div>
      ) : null}
    </div>
  )
}

function SkillEditor({
  skill,
  saving,
  error,
  onClose,
  onSave,
}: {
  skill: CustomSkillDetail
  saving: boolean
  error: string
  onClose: () => void
  onSave: (payload: UpdateCustomSkillRequest) => Promise<void>
}) {
  const { t } = useI18n()
  const [name, setName] = useState(skill.meta.name)
  const [description, setDescription] = useState(skill.meta.description)
  const [deviceTypes, setDeviceTypes] = useState(skill.meta.device_types.join(', '))
  const [triggerText, setTriggerText] = useState(skill.structured.trigger_text)
  const [actionText, setActionText] = useState(skill.structured.action_text)
  const [knowledgeMd, setKnowledgeMd] = useState(skill.content.knowledge_md)
  const [decideMd, setDecideMd] = useState(skill.content.decide_md)

  useEffect(() => {
    setName(skill.meta.name)
    setDescription(skill.meta.description)
    setDeviceTypes(skill.meta.device_types.join(', '))
    setTriggerText(skill.structured.trigger_text)
    setActionText(skill.structured.action_text)
    setKnowledgeMd(skill.content.knowledge_md)
    setDecideMd(skill.content.decide_md)
  }, [skill])

  const handleSave = async () => {
    await onSave({
      mode: 'structured',
      name: name.trim(),
      description: description.trim(),
      device_types: deviceTypes.split(',').map((item) => item.trim()).filter(Boolean),
      trigger_text: triggerText.trim(),
      action_text: actionText.trim(),
      knowledge_md: knowledgeMd,
      decide_md: decideMd,
    })
  }

  return (
    <div className="flex h-full w-[420px] flex-col border-l border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
        <div>
          <h3 className="text-base font-semibold text-slate-800">{t('skills.editCustomSkill')}</h3>
          <p className="text-xs text-slate-500">{skill.meta.folder_name}</p>
        </div>
        <button onClick={onClose} className="rounded-xl p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 cursor-pointer">
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
        <label className="block space-y-2">
          <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{t('skills.name')}</span>
          <input value={name} onChange={(event) => setName(event.target.value)} className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100" />
        </label>

        <label className="block space-y-2">
          <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{t('skills.description')}</span>
          <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} className="w-full resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100" />
        </label>

        <label className="block space-y-2">
          <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{t('skills.deviceTypes')}</span>
          <input value={deviceTypes} onChange={(event) => setDeviceTypes(event.target.value)} placeholder="speaker, curtain" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100" />
        </label>

        <label className="block space-y-2">
          <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{t('skills.trigger')}</span>
          <textarea value={triggerText} onChange={(event) => setTriggerText(event.target.value)} rows={4} className="w-full resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100" />
        </label>

        <label className="block space-y-2">
          <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{t('skills.action')}</span>
          <textarea value={actionText} onChange={(event) => setActionText(event.target.value)} rows={4} className="w-full resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100" />
        </label>

        <label className="block space-y-2">
          <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Knowledge</span>
          <textarea value={knowledgeMd} onChange={(event) => setKnowledgeMd(event.target.value)} rows={6} className="w-full resize-none rounded-xl border border-slate-200 px-3 py-2 font-mono text-xs text-slate-700 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100" />
        </label>

        <label className="block space-y-2">
          <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Decide Prompt</span>
          <textarea value={decideMd} onChange={(event) => setDecideMd(event.target.value)} rows={8} className="w-full resize-none rounded-xl border border-slate-200 px-3 py-2 font-mono text-xs text-slate-700 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100" />
        </label>

        {error ? <div className="rounded-xl border border-rose-100 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div> : null}
      </div>

      <div className="flex items-center justify-end gap-3 border-t border-slate-200 px-5 py-4">
        <button onClick={onClose} className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 transition hover:bg-slate-50 cursor-pointer">{t('skills.cancel')}</button>
        <button onClick={() => void handleSave()} disabled={saving} className="inline-flex items-center gap-2 rounded-xl bg-violet-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-violet-700 disabled:opacity-50 cursor-pointer">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <FilePenLine className="h-4 w-4" />}
          {t('skills.saveChanges')}
        </button>
      </div>
    </div>
  )
}

export default function SkillsPanel({ open, onClose }: SkillsPanelProps) {
  const { t } = useI18n()
  const { skills, loading, refresh } = useSkills(open ? 10000 : 30000)
  const [query, setQuery] = useState('')
  const [draft, setDraft] = useState('')
  const [createReply, setCreateReply] = useState('')
  const [createError, setCreateError] = useState('')
  const [creating, setCreating] = useState(false)
  const [selectedSkill, setSelectedSkill] = useState<SkillInventoryItem | null>(null)
  const [skillDetail, setSkillDetail] = useState<CustomSkillDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [saving, setSaving] = useState(false)

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
      setCreateReply(result.reply || t('skills.submitted'))
      setDraft('')
      await refresh()
    } catch (error) {
      const message = error instanceof Error ? error.message : t('skills.createFailed')
      setCreateError(message)
    } finally {
      setCreating(false)
    }
  }

  const handleOpenEditor = async (skill: SkillInventoryItem) => {
    setSelectedSkill(skill)
    setSkillDetail(null)
    setDetailLoading(true)
    setSaveError('')
    try {
      const detail = await api.getCustomSkillDetail(skill.folder_name)
      setSkillDetail(detail)
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : t('skills.readDetailFailed'))
      setSkillDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleCloseEditor = () => {
    setSelectedSkill(null)
    setSkillDetail(null)
    setSaveError('')
  }

  const handleSaveSkill = async (payload: UpdateCustomSkillRequest) => {
    if (!selectedSkill) return
    setSaving(true)
    setSaveError('')
    try {
      await api.updateCustomSkill(selectedSkill.folder_name, payload)
      const [detail] = await Promise.all([
        api.getCustomSkillDetail(selectedSkill.folder_name),
        refresh(),
      ])
      setSkillDetail(detail)
      setCreateReply(t('skills.savedReloaded'))
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : t('skills.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/30 px-6 py-8">
      <div className="flex h-full max-h-[92vh] w-full max-w-7xl overflow-hidden rounded-2xl bg-slate-50 shadow-xl ring-1 ring-slate-200">
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-violet-100 p-2 text-violet-600">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-800">{t('skills.title')}</h2>
              <p className="text-sm text-slate-400">{t('skills.subtitle')}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={refresh}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-50 cursor-pointer"
            >
              <RefreshCw className="h-4 w-4" />
              {t('skills.refresh')}
            </button>
            <button
              onClick={onClose}
              className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 cursor-pointer"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="border-b border-slate-200 bg-slate-50 px-6 py-4">
          <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-center gap-2">
                <div className="rounded-xl bg-violet-100 p-2 text-violet-700">
                  <Plus className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-800">{t('skills.createTitle')}</h3>
                  <p className="text-xs text-slate-500">{t('skills.createDesc')}</p>
                </div>
              </div>

              <div className="mt-4 flex gap-3">
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder={t('skills.createPlaceholder')}
                  rows={4}
                  className="min-h-[104px] flex-1 resize-none rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700 outline-none transition focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                />
                <button
                  onClick={handleCreateSkill}
                  disabled={creating || !draft.trim()}
                  className="inline-flex min-w-[128px] items-center justify-center gap-2 self-stretch rounded-xl bg-violet-600 px-4 py-3 text-sm font-medium text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                  <span>{creating ? t('skills.creating') : t('skills.createSkill')}</span>
                </button>
              </div>

              {createReply ? (
                <div className="mt-3 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm leading-6 text-emerald-800">
                  <span className="font-medium">Anima: </span>
                  {createReply}
                </div>
              ) : null}

              {createError ? (
                <div className="mt-3 rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-700">
                  {createError}
                </div>
              ) : null}
            </div>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
              <input
                type="text"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t('skills.searchPlaceholder')}
                className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
              />
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
                  <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-slate-400">
                    <Cpu className="h-3.5 w-3.5" />
                    <span>System</span>
                  </div>
                  <div className="mt-2 text-2xl font-semibold text-slate-800">{systemCount}</div>
                </div>
                <div className="rounded-xl border border-violet-100 bg-violet-50 px-4 py-3">
                  <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-violet-400">
                    <Bot className="h-3.5 w-3.5" />
                    <span>Custom</span>
                  </div>
                  <div className="mt-2 text-2xl font-semibold text-violet-700">{customCount}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid flex-1 gap-0 overflow-hidden md:grid-cols-2">
          <div className="overflow-y-auto border-r border-slate-200 bg-slate-50 px-6 py-5">
            <SectionTitle title={t('skills.systemSkills')} detail={t('skills.visible', { count: filtered.system.length })} />
            <div className="mt-4 space-y-3">
              {filtered.system.length ? filtered.system.map((skill) => (
                <SkillCard key={`system-${skill.folder_name}`} skill={skill} />
              )) : (
                <p className="text-sm text-slate-500">{loading ? t('skills.loadingSystem') : t('skills.noSystemMatch')}</p>
              )}
            </div>
          </div>

          <div className="overflow-y-auto bg-slate-50 px-6 py-5">
            <SectionTitle title={t('skills.customSkills')} detail={t('skills.visible', { count: filtered.custom.length })} />
            <div className="mt-4 space-y-3">
              {filtered.custom.length ? filtered.custom.map((skill) => (
                <SkillCard key={`custom-${skill.folder_name}`} skill={skill} onEdit={handleOpenEditor} />
              )) : (
                <p className="text-sm text-slate-500">{loading ? t('skills.loadingCustom') : t('skills.noCustom')}</p>
              )}
            </div>
          </div>
        </div>
        </div>

        {selectedSkill ? (
          detailLoading ? (
            <div className="flex h-full w-[420px] items-center justify-center border-l border-slate-200 bg-white">
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t('skills.loadingDetail')}
              </div>
            </div>
          ) : skillDetail ? (
            <SkillEditor
              skill={skillDetail}
              saving={saving}
              error={saveError}
              onClose={handleCloseEditor}
              onSave={handleSaveSkill}
            />
          ) : (
            <div className="flex h-full w-[420px] flex-col border-l border-slate-200 bg-white">
              <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
                <h3 className="text-base font-semibold text-slate-800">{t('skills.editCustomSkill')}</h3>
                <button onClick={handleCloseEditor} className="rounded-xl p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 cursor-pointer">
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="p-5 text-sm text-rose-700">{saveError || t('skills.detailFailed')}</div>
            </div>
          )
        ) : null}
      </div>
    </div>
  )
}
