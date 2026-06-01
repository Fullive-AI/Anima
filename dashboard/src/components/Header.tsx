import { useState, useEffect } from 'react'
import { RefreshCw, Wifi, WifiOff, Settings, HelpCircle, BrainCircuit, Sparkles } from 'lucide-react'
import { api } from '../hooks/useApi'
import { useI18n } from '../i18n/useI18n'

interface HeaderProps {
  deviceCount: number
  onScan: () => void
  onOpenSettings: () => void
  onOpenHelp: () => void
  onOpenMemory: () => void
  onOpenSkills: () => void
}

export default function Header({ deviceCount, onScan, onOpenSettings, onOpenHelp, onOpenMemory, onOpenSkills }: HeaderProps) {
  const [connected, setConnected] = useState(false)
  const [scanning, setScanning] = useState(false)
  const { language, setLanguage, t } = useI18n()

  useEffect(() => {
    api.getHealth().then(() => setConnected(true)).catch(() => setConnected(false))
    const id = setInterval(() => {
      api.getHealth().then(() => setConnected(true)).catch(() => setConnected(false))
    }, 10000)
    return () => clearInterval(id)
  }, [])

  const handleScan = async () => {
    setScanning(true)
    try {
      await api.scan()
      onScan()
    } finally {
      setTimeout(() => setScanning(false), 1000)
    }
  }

  return (
    <header className="flex h-16 items-center justify-between border-b border-slate-200/70 bg-white/95 px-6 shadow-[0_1px_2px_rgba(15,23,42,0.04)] backdrop-blur">
      <div className="flex min-w-0 items-center gap-3">
        <img
          src="/anima-logo.svg"
          alt="Anima"
          className="h-8 w-auto max-w-[136px] object-contain"
        />
        <span className="hidden whitespace-nowrap text-xs font-medium text-slate-400 lg:block">
          {t('header.tagline')}
        </span>
      </div>

      <div className="flex items-center gap-1.5">
        <div className={`mr-2 flex h-9 items-center gap-1.5 rounded-xl px-3 text-xs font-semibold ${
          connected
            ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100'
            : 'bg-red-50 text-red-600 ring-1 ring-red-100'
        }`}>
          {connected
            ? <><Wifi className="w-3.5 h-3.5" /><span>{t('common.online')}</span></>
            : <><WifiOff className="w-3.5 h-3.5" /><span>{t('common.offline')}</span></>
          }
        </div>

        <span className="mr-2 whitespace-nowrap text-xs font-medium text-slate-400">{t('header.deviceCount', { count: deviceCount })}</span>

        <button
          onClick={handleScan}
          disabled={scanning}
          className="flex h-9 cursor-pointer items-center gap-1.5 rounded-xl bg-violet-600 px-3.5 text-xs font-semibold text-white shadow-[0_6px_16px_rgba(124,58,237,0.22)] transition-all hover:bg-violet-700 hover:shadow-[0_8px_20px_rgba(124,58,237,0.28)] disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
          {t('header.scan')}
        </button>

        <div className="mx-1 h-5 w-px bg-slate-200" />

        <div className="flex h-9 items-center rounded-xl border border-slate-200 bg-slate-50 p-1">
          {[
            { value: 'zh-CN' as const, label: t('header.languageZh') },
            { value: 'en-US' as const, label: t('header.languageEn') },
          ].map((item) => (
            <button
              key={item.value}
              onClick={() => setLanguage(item.value)}
              className={`h-7 rounded-lg px-2.5 text-xs font-semibold transition-colors ${
                language === item.value
                  ? 'bg-violet-600 text-white shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {[
          { icon: Settings, label: t('header.settings'), onClick: onOpenSettings },
          { icon: HelpCircle, label: t('header.help'), onClick: onOpenHelp },
          { icon: BrainCircuit, label: t('header.memory'), onClick: onOpenMemory },
          { icon: Sparkles, label: t('header.skills'), onClick: onOpenSkills },
        ].map(({ icon: Icon, label, onClick }) => (
          <button
            key={label}
            onClick={onClick}
            title={label}
            className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
          >
            <Icon className="w-4 h-4" />
          </button>
        ))}
      </div>
    </header>
  )
}
