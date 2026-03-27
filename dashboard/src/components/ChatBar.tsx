import { useState } from 'react'
import { Send, MessageCircle, Loader2 } from 'lucide-react'
import { api } from '../hooks/useApi'

interface ChatBarProps {
  onDevicesChanged: () => void
}

export default function ChatBar({ onDevicesChanged }: ChatBarProps) {
  const [message, setMessage] = useState('')
  const [reply, setReply] = useState('')
  const [loading, setLoading] = useState(false)
  const [qrImage, setQrImage] = useState('')
  const [qrPolling, setQrPolling] = useState(false)

  const handleSend = async () => {
    const text = message.trim()
    if (!text || loading) return

    setLoading(true)
    setReply('')
    try {
      const res = await api.chat(text)
      setReply(res.reply)
      setQrImage(res.qr_image_b64 || '')
      setMessage('')

      if (res.refresh_devices) {
        onDevicesChanged()
      }

      if (res.status === 'qr_required' && res.qr_image_b64) {
        setQrPolling(true)
        const country = res.country || 'cn'
        const pollInterval = setInterval(async () => {
          try {
            const r = await fetch('/api/settings/xiaomi/qr/poll', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ country }),
            })
            const d = await r.json()
            if (d.status === 'qr_pending') return

            clearInterval(pollInterval)
            setQrPolling(false)
            setQrImage('')

            if (d.status === 'ok') {
              setReply(`连接成功：云端 ${d.cloud_devices || 0} 台设备，更新 ${d.updated || 0} 台，新增 ${d.registered || 0} 台。`)
              onDevicesChanged()
              return
            }

            setReply(d.error || '扫码登录失败')
          } catch {
            clearInterval(pollInterval)
            setQrPolling(false)
            setReply('扫码状态轮询失败，请稍后重试')
          }
        }, 2000)
      } else {
        setQrPolling(false)
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '连接失败，请检查后端是否运行'
      setReply(message)
      setQrPolling(false)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="border-t border-slate-200 bg-white px-6 py-3">
      {reply && (
        <div className="mb-2 px-3 py-2 bg-violet-50 rounded-lg text-sm text-slate-600 border border-violet-100">
          <span className="text-violet-600 font-medium">Anima: </span>{reply}
        </div>
      )}
      {qrImage && (
        <div className="mb-2 rounded-xl border border-violet-100 bg-white p-3">
          <img
            src={`data:image/png;base64,${qrImage}`}
            alt="米家扫码登录"
            className="mx-auto h-48 w-48 rounded-lg border border-slate-200"
          />
          <p className="mt-2 flex items-center justify-center gap-2 text-sm text-violet-600">
            <Loader2 className={`h-4 w-4 ${qrPolling ? 'animate-spin' : ''}`} />
            请让客户打开米家 App 扫码
          </p>
        </div>
      )}
      <div className="flex items-center gap-3">
        <MessageCircle className="w-5 h-5 text-slate-400" />
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="问问题、扫描设备，或直接让 Anima 调用 skill..."
          className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-4 py-2 text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:border-violet-400 focus:ring-1 focus:ring-violet-400 transition-colors"
        />
        <button
          onClick={handleSend}
          disabled={loading || !message.trim()}
          className="flex items-center gap-2 px-4 py-2 text-sm bg-violet-500 hover:bg-violet-600 disabled:opacity-40 text-white rounded-lg transition-colors cursor-pointer"
        >
          <Send className="w-4 h-4" />
          发送
        </button>
      </div>
    </div>
  )
}
