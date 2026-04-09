import { useState, useEffect } from 'react'
import { Activity, RefreshCw, Wifi, WifiOff, Settings, HelpCircle, BrainCircuit } from 'lucide-react'
import { api } from '../hooks/useApi'

interface HeaderProps {
  deviceCount: number
  onScan: () => void
  onOpenSettings: () => void
  onOpenHelp: () => void
  onOpenMemory: () => void
}

export default function Header({ deviceCount, onScan, onOpenSettings, onOpenHelp, onOpenMemory }: HeaderProps) {
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
    <header className="flex items-center justify-between px-6 py-4 bg-white border-b border-slate-200 shadow-sm">
      <div className="flex items-center gap-3">
        <Activity className="w-6 h-6 text-violet-500" />
        <h1 className="text-xl font-semibold text-slate-800">Anima</h1>
        <span className="text-sm text-slate-400">Make Every Hardware Intelligent</span>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 text-sm">
          {connected ? (
            <><Wifi className="w-4 h-4 text-emerald-500" /><span className="text-emerald-600">在线</span></>
          ) : (
            <><WifiOff className="w-4 h-4 text-red-400" /><span className="text-red-500">离线</span></>
          )}
        </div>

        <span className="text-sm text-slate-400">
          {deviceCount} 台设备
        </span>

        <button
          onClick={handleScan}
          disabled={scanning}
          className="flex items-center gap-2 px-3 py-1.5 text-sm bg-violet-500 hover:bg-violet-600 disabled:opacity-50 text-white rounded-lg transition-colors cursor-pointer"
        >
          <RefreshCw className={`w-4 h-4 ${scanning ? 'animate-spin' : ''}`} />
          扫描设备
        </button>

        <button
          onClick={onOpenSettings}
          className="p-2 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer"
          title="设置"
        >
          <Settings className="w-5 h-5 text-slate-500" />
        </button>

        <button
          onClick={onOpenHelp}
          className="p-2 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer"
          title="使用帮助"
        >
          <HelpCircle className="w-5 h-5 text-slate-500" />
        </button>

        <button
          onClick={onOpenMemory}
          className="p-2 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer"
          title="记忆调试"
        >
          <BrainCircuit className="w-5 h-5 text-slate-500" />
        </button>
      </div>
    </header>
  )
}
