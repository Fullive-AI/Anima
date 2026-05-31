import { X, ScanLine, Settings, Key, MessageCircle, Brain, BrainCircuit, BookOpen } from 'lucide-react'
import { useI18n } from '../i18n/useI18n'

interface HelpPanelProps {
  open: boolean
  onClose: () => void
}

export default function HelpPanel({ open, onClose }: HelpPanelProps) {
  const { t } = useI18n()
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[85vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <h2 className="text-lg font-semibold text-slate-800">{t('help.title')}</h2>
          <button onClick={onClose} className="p-1 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer">
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>

        <div className="p-6 space-y-6 text-sm text-slate-600 leading-relaxed">

          {/* Step 1 */}
          <section>
            <div className="flex items-center gap-2 mb-2">
              <span className="w-6 h-6 rounded-full bg-violet-500 text-white text-xs flex items-center justify-center font-bold">1</span>
              <h3 className="font-semibold text-slate-800">{t('help.llmTitle')}</h3>
            </div>
            <div className="ml-8 space-y-1">
              <p><Settings className="w-4 h-4 inline text-slate-400" /> {t('help.llm1')}</p>
              <p>{t('help.llm2')}</p>
              <p>{t('help.llm3')}</p>
              <p className="text-slate-400">{t('help.llm4')}</p>
            </div>
          </section>

          {/* Step 2 */}
          <section>
            <div className="flex items-center gap-2 mb-2">
              <span className="w-6 h-6 rounded-full bg-violet-500 text-white text-xs flex items-center justify-center font-bold">2</span>
              <h3 className="font-semibold text-slate-800">{t('help.xiaomiTitle')}</h3>
            </div>
            <div className="ml-8 space-y-1">
              <p><Settings className="w-4 h-4 inline text-slate-400" /> {t('help.xiaomi1')}</p>
              <p>{t('help.xiaomi2')}</p>
              <p>{t('help.xiaomi3')}</p>
              <p className="text-slate-400">{t('help.xiaomi4')}</p>
            </div>
            <div className="ml-8 mt-2 bg-amber-50 border border-amber-100 rounded-lg p-3 text-xs space-y-1">
              <p className="font-medium text-amber-700">{t('help.faq')}</p>
              <p>{t('help.faqToken')}</p>
              <p>{t('help.faqCloud')}</p>
              <p>{t('help.faqOffline')}</p>
            </div>
          </section>

          {/* Step 3 */}
          <section>
            <div className="flex items-center gap-2 mb-2">
              <span className="w-6 h-6 rounded-full bg-violet-500 text-white text-xs flex items-center justify-center font-bold">3</span>
              <h3 className="font-semibold text-slate-800">{t('help.manageTitle')}</h3>
            </div>
            <div className="ml-8 space-y-1">
              <p>{t('help.manage1')}</p>
              <p>{t('help.manage2')}</p>
              <p><ScanLine className="w-4 h-4 inline text-slate-400" /> {t('help.manage3')}</p>
            </div>
          </section>

          {/* Step 4 */}
          <section>
            <div className="flex items-center gap-2 mb-2">
              <span className="w-6 h-6 rounded-full bg-violet-500 text-white text-xs flex items-center justify-center font-bold">4</span>
              <h3 className="font-semibold text-slate-800">{t('help.aiTitle')}</h3>
            </div>
            <div className="ml-8 space-y-1">
              <p>{t('help.ai1')}</p>
              <p><Brain className="w-4 h-4 inline text-slate-400" /> {t('help.ai2')}</p>
              <p className="text-slate-400">{t('help.ai3')}</p>
            </div>
          </section>

          {/* Step 5 */}
          <section>
            <div className="flex items-center gap-2 mb-2">
              <span className="w-6 h-6 rounded-full bg-violet-500 text-white text-xs flex items-center justify-center font-bold">5</span>
              <h3 className="font-semibold text-slate-800">{t('help.chatTitle')}</h3>
            </div>
            <div className="ml-8 space-y-1">
              <p><MessageCircle className="w-4 h-4 inline text-slate-400" /> {t('help.chat1')}</p>
              <p>{t('help.chat2')}</p>
            </div>
          </section>

          <section>
            <div className="flex items-center gap-2 mb-2">
              <span className="w-6 h-6 rounded-full bg-violet-500 text-white text-xs flex items-center justify-center font-bold">6</span>
              <h3 className="font-semibold text-slate-800">{t('help.memoryTitle')}</h3>
            </div>
            <div className="ml-8 space-y-1">
              <p><BrainCircuit className="w-4 h-4 inline text-slate-400" /> {t('help.memory1')}</p>
              <p>{t('help.memory2')}</p>
              <p className="text-slate-400">{t('help.memory3')}</p>
            </div>
          </section>

          <hr className="border-slate-200" />

          {/* Manual device */}
          <section>
            <div className="flex items-center gap-2 mb-2">
              <Key className="w-4 h-4 text-violet-500" />
              <h3 className="font-semibold text-slate-800">{t('help.manualTitle')}</h3>
            </div>
            <div className="ml-6 space-y-1">
              <p>{t('help.manual1')}</p>
              <p>{t('help.manual2')}</p>
            </div>
          </section>

          {/* Links */}
          <section>
            <div className="flex items-center gap-2 mb-2">
              <BookOpen className="w-4 h-4 text-violet-500" />
              <h3 className="font-semibold text-slate-800">{t('help.moreTitle')}</h3>
            </div>
            <div className="ml-6 space-y-1">
              <p>
                <a href="https://github.com/fulai-tech/Anima" target="_blank" className="text-violet-500 hover:text-violet-600 underline">
                  {t('help.github')}
                </a>
                {' · '}
                <a href="https://github.com/fulai-tech/Anima/blob/main/README.zh-CN.md" target="_blank" className="text-violet-500 hover:text-violet-600 underline">
                  {t('help.docsZh')}
                </a>
              </p>
              <p>
                <a href="/docs" target="_blank" className="text-violet-500 hover:text-violet-600 underline">
                  FastAPI Swagger /docs
                </a>
              </p>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
