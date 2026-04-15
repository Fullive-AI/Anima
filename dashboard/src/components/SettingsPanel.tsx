import { useState, useEffect } from 'react'
import { Wifi, WifiOff, Brain, Eye, EyeOff, X, Check, Loader2, Plus, Monitor, Settings, Cpu } from 'lucide-react'
import { api } from '../hooks/useApi'

interface SettingsPanelProps {
  open: boolean
  onClose: () => void
  onDevicesChanged: () => void
}

export default function SettingsPanel({ open, onClose, onDevicesChanged }: SettingsPanelProps) {
  // Xiaomi state
  const [xiaomiCountry, setXiaomiCountry] = useState('cn')
  const [xiaomiConnected, setXiaomiConnected] = useState(false)
  const [xiaomiDeviceCount, setXiaomiDeviceCount] = useState(0)
  const [xiaomiError, setXiaomiError] = useState('')
  const [xiaomiResult, setXiaomiResult] = useState('')
  const [qrImage, setQrImage] = useState('')
  const [qrPolling, setQrPolling] = useState(false)

  // LLM state
  const [llmKey, setLlmKey] = useState('')        // masked key for display
  const [llmNewKey, setLlmNewKey] = useState('')   // new key input
  const [llmModel, setLlmModel] = useState('gpt-4o')
  const [llmBaseUrl, setLlmBaseUrl] = useState('')
  const [llmDisableThinking, setLlmDisableThinking] = useState(false)
  const [llmConfigured, setLlmConfigured] = useState(false)
  const [llmSource, setLlmSource] = useState('')
  const [llmSaving, setLlmSaving] = useState(false)
  const [llmSaved, setLlmSaved] = useState(false)
  const [llmEditing, setLlmEditing] = useState(false)

  // Manual device state
  const [manualIp, setManualIp] = useState('')
  const [manualToken, setManualToken] = useState('')
  const [manualName, setManualName] = useState('')
  const [manualType, setManualType] = useState('unknown')
  const [manualAdding, setManualAdding] = useState(false)
  const [manualResult, setManualResult] = useState('')
  const [manualError, setManualError] = useState('')

  const [showKey, setShowKey] = useState(false)

  // Virtual device state
  const [virtualName, setVirtualName] = useState('')
  const [virtualType, setVirtualType] = useState('light')
  const [virtualAdding, setVirtualAdding] = useState(false)
  const [virtualResult, setVirtualResult] = useState('')

  useEffect(() => {
    if (!open) return
    // Load current status
    fetch('/api/settings/xiaomi/status').then(r => r.json()).then(data => {
      setXiaomiConnected(data.configured)
      setXiaomiDeviceCount(data.device_count || 0)
      if (data.country) setXiaomiCountry(data.country)
    }).catch(() => {})

    fetch('/api/settings/llm/status').then(r => r.json()).then(data => {
      setLlmConfigured(data.configured)
      setLlmModel(data.model || 'gpt-4o')
      setLlmBaseUrl(data.base_url || '')
      setLlmSource(data.source || '')
      setLlmDisableThinking(data.disable_thinking || false)
      if (data.masked_key) setLlmKey(data.masked_key)
    }).catch(() => {})
  }, [open])

  const handleStartQr = async () => {
    setXiaomiError('')
    setXiaomiResult('')
    setQrImage('')
    try {
      const res = await fetch('/api/settings/xiaomi/qr/start', { method: 'POST' })
      const data = await res.json()
      if (data.success && data.qr_image_b64) {
        setQrImage(data.qr_image_b64)
        setQrPolling(true)
        // Start polling
        const pollInterval = setInterval(async () => {
          try {
            const r = await fetch('/api/settings/xiaomi/qr/poll', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ country: xiaomiCountry }),
            })
            const d = await r.json()
            if (d.status === 'qr_pending') return // keep waiting
            clearInterval(pollInterval)
            setQrPolling(false)
            setQrImage('')
            if (d.status === 'ok') {
              setXiaomiConnected(true)
              setXiaomiDeviceCount(d.cloud_devices || 0)
              const msg = `连接成功！云端 ${d.cloud_devices} 台设备，更新 ${d.updated || 0} 台，新增 ${d.registered} 台。`
              setXiaomiResult(msg + (d.updated === 0 && d.registered > 0 ? '' : d.updated === 0 ? ' 如仍有设备显示"需要激活"，可能绑在其他小米账号下，请用那个账号再扫一次。' : ''))
              onDevicesChanged()
            } else {
              setXiaomiError(d.error || '登录失败')
            }
          } catch {
            clearInterval(pollInterval)
            setQrPolling(false)
            setQrImage('')
            setXiaomiError('网络错误')
          }
        }, 2000)
      } else {
        setXiaomiError(data.error || '获取二维码失败')
      }
    } catch {
      setXiaomiError('网络错误')
    }
  }

  const handleXiaomiDisconnect = async () => {
    await fetch('/api/settings/xiaomi/disconnect', { method: 'POST' })
    setXiaomiConnected(false)
    setXiaomiDeviceCount(0)
    setXiaomiResult('')
  }

  const handleLlmSave = async () => {
    if (!llmNewKey) return
    setLlmSaving(true)
    setLlmSaved(false)

    try {
      await fetch('/api/settings/llm/configure', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_key: llmNewKey,
          model: llmModel,
          base_url: llmBaseUrl,
          disable_thinking: llmDisableThinking,
        }),
      })
      setLlmConfigured(true)
      setLlmSaved(true)
      setLlmSource('dashboard')
      setLlmKey(llmNewKey.slice(0, 8) + '***')
      setLlmNewKey('')
      setLlmEditing(false)
      setTimeout(() => setLlmSaved(false), 3000)
    } catch {
      /* ignore */
    } finally {
      setLlmSaving(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[85vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-violet-500" />
            <h2 className="text-lg font-semibold text-slate-800">设置</h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer">
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Xiaomi Section */}
          <section>
            <div className="flex items-center gap-2 mb-3">
              {xiaomiConnected ? <Wifi className="w-4 h-4 text-emerald-500" /> : <WifiOff className="w-4 h-4 text-slate-400" />}
              <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">小米 / 米家</h3>
              {xiaomiConnected && <span className="text-xs bg-emerald-50 text-emerald-600 px-2 py-0.5 rounded-full">已连接 · {xiaomiDeviceCount} 台设备</span>}
            </div>

            {xiaomiConnected && !qrImage ? (
              <div>
                <p className="text-sm text-slate-500 mb-2">已获取 {xiaomiDeviceCount} 台设备的信息和 Token。</p>
                {xiaomiResult && <p className="text-sm text-emerald-600 mb-2">{xiaomiResult}</p>}
                <div className="flex gap-3">
                  <button onClick={handleStartQr} className="text-sm text-violet-500 hover:text-violet-600 cursor-pointer">重新扫码刷新</button>
                  <button onClick={handleXiaomiDisconnect} className="text-sm text-red-500 hover:text-red-600 cursor-pointer">断开连接</button>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-slate-500">
                  用米家 APP 扫码登录，自动获取所有设备和 Token。无需输入账号密码，成功率极高。
                </p>

                <select
                  value={xiaomiCountry}
                  onChange={e => setXiaomiCountry(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-slate-50 focus:outline-none focus:border-violet-400"
                >
                  <option value="cn">中国大陆</option>
                  <option value="tw">台湾</option>
                  <option value="de">欧洲</option>
                  <option value="us">美国</option>
                  <option value="sg">新加坡</option>
                  <option value="in">印度</option>
                  <option value="ru">俄罗斯</option>
                </select>

                {qrImage ? (
                  <div className="text-center space-y-2">
                    <img
                      src={`data:image/png;base64,${qrImage}`}
                      alt="扫码登录"
                      className="mx-auto w-48 h-48 rounded-xl border border-slate-200"
                    />
                    <p className="text-sm text-violet-600 flex items-center justify-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      请用米家 APP 扫码...
                    </p>
                  </div>
                ) : (
                  <button
                    onClick={handleStartQr}
                    disabled={qrPolling}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2 text-sm bg-violet-500 hover:bg-violet-600 disabled:opacity-40 text-white rounded-lg transition-colors cursor-pointer"
                  >
                    <Wifi className="w-4 h-4" />
                    生成二维码
                  </button>
                )}

                {xiaomiError && <p className="text-sm text-red-500">{xiaomiError}</p>}
                {xiaomiResult && <p className="text-sm text-emerald-600">{xiaomiResult}</p>}
              </div>
            )}
          </section>

          <hr className="border-slate-200" />

          {/* Manual Device Section */}
          <section>
            <div className="flex items-center gap-2 mb-3">
              <Plus className="w-4 h-4 text-violet-500" />
              <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">手动添加设备</h3>
            </div>

            <p className="text-sm text-slate-500 mb-3">
              输入设备 IP 和 Token 直接添加。Token 可从米家 APP 日志或
              <a href="https://github.com/PiotrMachworksdev/xiaomi-token-extractor" target="_blank" className="text-violet-500 hover:text-violet-600"> Token 提取工具 </a>
              获取。
            </p>

            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <input
                  type="text"
                  placeholder="设备 IP (如 192.168.1.100)"
                  value={manualIp}
                  onChange={e => setManualIp(e.target.value)}
                  className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-slate-50 focus:outline-none focus:border-violet-400"
                />
                <input
                  type="text"
                  placeholder="设备名称（可选）"
                  value={manualName}
                  onChange={e => setManualName(e.target.value)}
                  className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-slate-50 focus:outline-none focus:border-violet-400"
                />
              </div>
              <input
                type="text"
                placeholder="Token (32 位十六进制)"
                value={manualToken}
                onChange={e => setManualToken(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-slate-50 font-mono focus:outline-none focus:border-violet-400"
              />
              <select
                value={manualType}
                onChange={e => setManualType(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-slate-50 focus:outline-none focus:border-violet-400"
              >
                <option value="unknown">自动识别</option>
                <option value="humidifier">加湿器</option>
                <option value="air_conditioner">空调</option>
                <option value="light">灯光</option>
                <option value="air_purifier">空气净化器</option>
                <option value="vacuum">扫地机器人</option>
                <option value="plug">智能插座</option>
                <option value="curtain">窗帘</option>
                <option value="sensor">传感器</option>
              </select>

              {manualError && <p className="text-sm text-red-500">{manualError}</p>}
              {manualResult && <p className="text-sm text-emerald-600">{manualResult}</p>}

              <button
                onClick={async () => {
                  if (!manualIp || !manualToken) return
                  setManualAdding(true)
                  setManualError('')
                  setManualResult('')
                  try {
                    const res = await fetch('/api/devices/add', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ ip: manualIp, token: manualToken, name: manualName, device_type: manualType }),
                    })
                    const data = await res.json()
                    if (data.success) {
                      setManualResult(`已添加: ${data.name} (${data.type})`)
                      setManualIp('')
                      setManualToken('')
                      setManualName('')
                      setManualType('unknown')
                      onDevicesChanged()
                    } else {
                      setManualError(data.error || '添加失败')
                    }
                  } catch {
                    setManualError('网络错误')
                  } finally {
                    setManualAdding(false)
                  }
                }}
                disabled={manualAdding || !manualIp || !manualToken}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 text-sm bg-violet-500 hover:bg-violet-600 disabled:opacity-40 text-white rounded-lg transition-colors cursor-pointer"
              >
                {manualAdding ? <Loader2 className="w-4 h-4 animate-spin" /> : <Monitor className="w-4 h-4" />}
                添加设备
              </button>
            </div>
          </section>

          <hr className="border-slate-200" />

          {/* LLM Section */}
          <section>
            <div className="flex items-center gap-2 mb-3">
              <Brain className="w-4 h-4 text-violet-500" />
              <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">LLM 大脑</h3>
              {llmConfigured && <span className="text-xs bg-emerald-50 text-emerald-600 px-2 py-0.5 rounded-full">已配置 ({llmSource})</span>}
            </div>

            {llmConfigured && !llmEditing ? (
              <div className="space-y-2">
                <div className="px-3 py-2 bg-slate-50 rounded-lg border border-slate-200 text-sm">
                  <div className="flex justify-between"><span className="text-slate-400">API Key</span><span className="font-mono text-slate-600">{llmKey || '***'}</span></div>
                  <div className="flex justify-between mt-1"><span className="text-slate-400">模型</span><span className="text-slate-600">{llmModel}</span></div>
                  {llmBaseUrl && <div className="flex justify-between mt-1"><span className="text-slate-400">Base URL</span><span className="text-slate-600 truncate ml-4">{llmBaseUrl}</span></div>}
                  {llmDisableThinking && <div className="flex justify-between mt-1"><span className="text-slate-400">深度思考</span><span className="text-slate-600">已关闭</span></div>}
                </div>
                <button onClick={() => setLlmEditing(true)} className="text-sm text-violet-500 hover:text-violet-600 cursor-pointer">修改配置</button>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-slate-500">
                  配置 AI 大脑，支持 OpenAI / DeepSeek / 豆包 / Ollama 等兼容 OpenAI API 的服务。
                  也可通过 .env 文件配置。
                </p>
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'}
                    placeholder="API Key"
                    value={llmNewKey}
                    onChange={e => setLlmNewKey(e.target.value)}
                    className="w-full px-3 py-2 pr-10 text-sm border border-slate-200 rounded-lg bg-slate-50 focus:outline-none focus:border-violet-400"
                  />
                  <button onClick={() => setShowKey(!showKey)} className="absolute right-2 top-1/2 -translate-y-1/2 p-1 cursor-pointer">
                    {showKey ? <EyeOff className="w-4 h-4 text-slate-400" /> : <Eye className="w-4 h-4 text-slate-400" />}
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <input
                    type="text"
                    placeholder="模型名称 (如 gpt-4o)"
                    value={llmModel}
                    onChange={e => setLlmModel(e.target.value)}
                    className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-slate-50 focus:outline-none focus:border-violet-400"
                  />
                  <input
                    type="text"
                    placeholder="Base URL（留空=OpenAI）"
                    value={llmBaseUrl}
                    onChange={e => setLlmBaseUrl(e.target.value)}
                    className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-slate-50 focus:outline-none focus:border-violet-400"
                  />
                </div>
                <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={llmDisableThinking}
                    onChange={e => setLlmDisableThinking(e.target.checked)}
                    className="rounded"
                  />
                  关闭深度思考（豆包必选）
                </label>

                {llmSaved && <p className="text-sm text-emerald-600 flex items-center gap-1"><Check className="w-4 h-4" />已保存</p>}

                <div className="flex gap-2">
                  {llmConfigured && (
                    <button onClick={() => setLlmEditing(false)} className="flex-1 px-4 py-2 text-sm border border-slate-200 text-slate-600 rounded-lg hover:bg-slate-50 transition-colors cursor-pointer">
                      取消
                    </button>
                  )}
                  <button
                    onClick={handleLlmSave}
                    disabled={llmSaving || !llmNewKey}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-sm bg-violet-500 hover:bg-violet-600 disabled:opacity-40 text-white rounded-lg transition-colors cursor-pointer"
                  >
                    {llmSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Brain className="w-4 h-4" />}
                    保存 LLM 配置
                  </button>
                </div>
              </div>
            )}
          </section>

          <hr className="border-slate-200" />

          {/* Virtual Device Section */}
          <section>
            <div className="flex items-center gap-2 mb-3">
              <Cpu className="w-4 h-4 text-violet-500" />
              <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">虚拟设备</h3>
            </div>
            <p className="text-sm text-slate-500 mb-3">创建虚拟设备用于测试，行为与真实设备完全一致。</p>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <input
                  type="text"
                  placeholder="设备名称（如：客厅灯）"
                  value={virtualName}
                  onChange={e => setVirtualName(e.target.value)}
                  className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-slate-50 focus:outline-none focus:border-violet-400"
                />
                <select
                  value={virtualType}
                  onChange={e => setVirtualType(e.target.value)}
                  className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-slate-50 focus:outline-none focus:border-violet-400"
                >
                  <option value="light">灯光</option>
                  <option value="humidifier">加湿器</option>
                  <option value="air_conditioner">空调</option>
                  <option value="air_purifier">空气净化器</option>
                </select>
              </div>
              {virtualResult && <p className="text-sm text-emerald-600">{virtualResult}</p>}
              <button
                onClick={async () => {
                  if (!virtualName.trim()) return
                  setVirtualAdding(true)
                  setVirtualResult('')
                  try {
                    const data = await api.createVirtualDevice(virtualName.trim(), virtualType)
                    setVirtualResult(`已创建: ${data.name}`)
                    setVirtualName('')
                    onDevicesChanged()
                    setTimeout(() => setVirtualResult(''), 3000)
                  } catch {
                    setVirtualResult('创建失败')
                  } finally {
                    setVirtualAdding(false)
                  }
                }}
                disabled={virtualAdding || !virtualName.trim()}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 text-sm bg-violet-500 hover:bg-violet-600 disabled:opacity-40 text-white rounded-lg transition-colors cursor-pointer"
              >
                {virtualAdding ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                创建虚拟设备
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
