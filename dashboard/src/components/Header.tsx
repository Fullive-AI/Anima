import { useState, useEffect } from 'react'
import { Activity, RefreshCw, Wifi, WifiOff, Settings, HelpCircle, BrainCircuit, Sparkles } from 'lucide-react'
import { api } from '../hooks/useApi'

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
    <header className="flex items-center justify-between px-6 py-3.5 bg-white border-b border-slate-200/80 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
      <div className="flex items-center gap-3">
        <div className="flex items-center justify-center w-8 h-8 rounded-xl bg-violet-600 shadow-sm">
          <Activity className="w-4 h-4 text-white" />
        </div>
        <h1 className="text-base font-semibold text-slate-900 tracking-tight">Anima</h1>
        <span className="hidden sm:block text-xs text-slate-400 font-medium">Make Every Hardware Intelligent</span>
      </div>

      <div className="flex items-center gap-1.5">
        <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium mr-2 ${
          connected
            ? 'bg-emerald-50 text-emerald-700'
            : 'bg-red-50 text-red-600'
        }`}>
          {connected
            ? <><Wifi className="w-3.5 h-3.5" /><span>在线</span></>
            : <><WifiOff className="w-3.5 h-3.5" /><span>离线</span></>
          }
        </div>

        <span className="text-xs text-slate-400 mr-2">{deviceCount} 台设备</span>

        <button
          onClick={handleScan}
          disabled={scanning}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-violet-600 hover:bg-violet-700 disabled:opacity-50 text-white rounded-lg transition-colors cursor-pointer shadow-sm"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
          扫描
        </button>

        <div className="w-px h-5 bg-slate-200 mx-1" />

        {[
          { icon: Settings, label: '设置', onClick: onOpenSettings },
          { icon: HelpCircle, label: '使用帮助', onClick: onOpenHelp },
          { icon: BrainCircuit, label: '记忆调试', onClick: onOpenMemory },
          { icon: Sparkles, label: '技能中心', onClick: onOpenSkills },
        ].map(({ icon: Icon, label, onClick }) => (
          <button
            key={label}
            onClick={onClick}
            title={label}
            className="p-2 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer text-slate-500 hover:text-slate-700"
          >
            <Icon className="w-4 h-4" />
          </button>
        ))}
      </div>
    </header>
  )
}
