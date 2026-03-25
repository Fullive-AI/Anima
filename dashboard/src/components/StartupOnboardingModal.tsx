import { useEffect, useState } from 'react'
import { Loader2, QrCode, X } from 'lucide-react'

interface StartupOnboardingModalProps {
  onDevicesChanged: () => void
}

interface OnboardingState {
  status: 'idle' | 'connected' | 'qr_required' | 'error'
  qr_image_b64?: string
  country?: string
  error?: string
}

export default function StartupOnboardingModal({ onDevicesChanged }: StartupOnboardingModalProps) {
  const [state, setState] = useState<OnboardingState>({ status: 'idle' })
  const [visible, setVisible] = useState(false)
  const [polling, setPolling] = useState(false)

  useEffect(() => {
    let active = true
    let timer: number | null = null

    async function loadStatus() {
      try {
        const res = await fetch('/api/onboarding/status')
        const data = await res.json() as OnboardingState
        if (!active) return

        setState(data)
        if (data.status === 'qr_required') {
          setVisible(true)
          return
        }

        if (data.status === 'idle') {
          timer = window.setTimeout(loadStatus, 2000)
          return
        }

        setVisible(false)
      } catch {
        if (!active) return
        timer = window.setTimeout(loadStatus, 2000)
      }
    }

    loadStatus()
    return () => {
      active = false
      if (timer) {
        window.clearTimeout(timer)
      }
    }
  }, [])

  useEffect(() => {
    if (state.status !== 'qr_required' || !visible) return

    let active = true
    const country = state.country || 'cn'
    setPolling(true)

    const timer = window.setInterval(async () => {
      try {
        const res = await fetch('/api/settings/xiaomi/qr/poll', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ country }),
        })
        const data = await res.json()
        if (!active || data.status === 'qr_pending') return

        window.clearInterval(timer)
        setPolling(false)

        if (data.status === 'ok') {
          setVisible(false)
          setState({ status: 'connected' })
          onDevicesChanged()
          return
        }

        setVisible(false)
        setState({ status: 'error', error: data.error || '扫码登录失败' })
      } catch {
        if (!active) return
        window.clearInterval(timer)
        setPolling(false)
        setVisible(false)
        setState({ status: 'error', error: '扫码状态轮询失败' })
      }
    }, 2000)

    return () => {
      active = false
      window.clearInterval(timer)
      setPolling(false)
    }
  }, [state.status, state.country, visible, onDevicesChanged])

  if (!visible || state.status !== 'qr_required' || !state.qr_image_b64) {
    return null
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/35 p-4">
      <div className="w-full max-w-md rounded-3xl border border-violet-100 bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-violet-100 p-3">
              <QrCode className="h-6 w-6 text-violet-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-900">连接小米设备</h2>
              <p className="text-sm text-slate-500">启动后已自动扫描，并生成了米家登录二维码。</p>
            </div>
          </div>
          <button
            onClick={() => setVisible(false)}
            className="rounded-lg p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
            title="关闭"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <img
          src={`data:image/png;base64,${state.qr_image_b64}`}
          alt="米家扫码登录"
          className="mx-auto h-64 w-64 rounded-2xl border border-slate-200"
        />

        <p className="mt-4 flex items-center justify-center gap-2 text-sm text-violet-700">
          <Loader2 className={`h-4 w-4 ${polling ? 'animate-spin' : ''}`} />
          请让用户打开米家 App 扫码登录
        </p>

        <p className="mt-2 text-center text-xs text-slate-500">
          登录成功后，Anima 会自动拉取屋内设备并刷新列表。
        </p>
      </div>
    </div>
  )
}
