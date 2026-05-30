import { useEffect, useState, type Dispatch, type SetStateAction } from 'react'
import { Droplets, Thermometer, Lightbulb, Zap, Power, Gauge, Key, Loader2, Check, FlaskConical, ChevronDown, ChevronRight } from 'lucide-react'
import { api, type Device, type CapabilityInput, type DeviceCapability } from '../hooks/useApi'

const SENSOR_ICONS: Record<string, typeof Gauge> = {
  humidity: Droplets,
  temperature: Thermometer,
  brightness: Lightbulb,
  power: Power,
  water_level: Gauge,
  color_temp: Zap,
}

interface DeviceCardProps {
  devices: Device[]
  selectedId: string | null
  onDevicesChanged?: () => void
}

type CapabilityValueState = Record<string, string | number | boolean>

function SensorBadge({ name, value, unit }: { name: string; value: unknown; unit: string }) {
  const Icon = SENSOR_ICONS[name] || Gauge
  const isOnOff = unit === 'on/off'
  const display = value !== null && value !== undefined
    ? isOnOff ? (value ? '开' : '关') : `${value}${unit}`
    : '--'

  return (
    <div className="flex min-h-[70px] items-center gap-2 rounded-2xl border border-slate-200/60 bg-slate-50/80 px-3 py-2.5 transition-colors hover:bg-white">
      <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-slate-100 bg-white shadow-sm">
        <Icon className="h-3.5 w-3.5 text-violet-500" />
      </div>
      <div className="min-w-0">
        <p className="truncate text-[10px] font-semibold capitalize tracking-wide text-slate-400">{name}</p>
        <p className="font-mono text-base font-semibold leading-tight text-slate-700">{display}</p>
      </div>
    </div>
  )
}

function NeedsTokenCard({ device, onActivated }: { device: Device; onActivated: () => void }) {
  const [token, setToken] = useState('')
  const [activating, setActivating] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [showTokenInput, setShowTokenInput] = useState(false)

  const handleActivate = async () => {
    if (!token || token.length < 16) {
      setError('Token 格式不正确（应为 32 位十六进制）')
      return
    }
    setActivating(true)
    setError('')
    try {
      const res = await fetch(`/api/devices/${device.device_id}/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      })
      const data = await res.json()
      if (data.success) {
        setSuccess(`已激活: ${data.name} (${data.type})`)
        setToken('')
        onActivated()
      } else {
        setError(data.error || '激活失败')
      }
    } catch {
      setError('网络错误')
    } finally {
      setActivating(false)
    }
  }

  return (
    <div className="rounded-[22px] border border-amber-200/70 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_rgba(15,23,42,0.05)]">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-slate-800">{device.name}</h3>
          <p className="text-xs text-slate-400 mt-0.5">{device.ip || device.device_id}</p>
        </div>
        <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-600">
          需要激活
        </span>
      </div>

      <div className="mb-4 space-y-1.5 rounded-2xl border border-amber-100 bg-amber-50/50 p-3 text-sm text-slate-600">
        <p className="font-medium text-slate-700 text-xs">已在局域网发现此设备，但缺少 Token。</p>
        <ol className="ml-4 list-decimal space-y-1 text-xs text-slate-500">
          <li>扫码登录小米/米家账号获取 Token</li>
          <li>如果设备还需要 Token，说明它绑定在另一个小米账号下</li>
          <li>如果你已有 Token，也可以在这里手动输入</li>
        </ol>
      </div>

      {showTokenInput ? (
        <div className="space-y-2">
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="输入 32 位 Token"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-mono transition-all focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
            />
            <button
              onClick={handleActivate}
              disabled={activating || !token}
              className="flex cursor-pointer items-center gap-1.5 rounded-xl bg-violet-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-violet-700 disabled:opacity-40"
            >
              {activating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Key className="h-4 w-4" />}
              激活
            </button>
          </div>
          <button onClick={() => setShowTokenInput(false)} className="cursor-pointer text-xs text-slate-400 hover:text-slate-500">收起</button>
        </div>
      ) : (
        <button onClick={() => setShowTokenInput(true)} className="cursor-pointer text-sm font-medium text-violet-600 hover:text-violet-700">
          输入 Token →
        </button>
      )}
      {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
      {success && <p className="mt-2 flex items-center gap-1 text-xs text-emerald-600"><Check className="h-3.5 w-3.5" />{success}</p>}
    </div>
  )
}

// Sensor labels for virtual device editing
const SENSOR_LABELS: Record<string, string> = {
  temperature: '温度 (°C)',
  humidity: '湿度 (%)',
  pm2_5: 'PM2.5 (µg/m³)',
  aqi: 'AQI',
  water_level: '水位 (%)',
  brightness: '亮度 (%)',
  color_temp: '色温 (K)',
}

// Sensor ranges for sliders
const SENSOR_RANGES: Record<string, { min: number; max: number; step: number }> = {
  temperature: { min: -10, max: 50, step: 0.5 },
  humidity: { min: 0, max: 100, step: 1 },
  pm2_5: { min: 0, max: 500, step: 1 },
  aqi: { min: 0, max: 500, step: 1 },
  water_level: { min: 0, max: 100, step: 1 },
  brightness: { min: 0, max: 100, step: 1 },
  color_temp: { min: 2700, max: 6500, step: 100 },
}

function VirtualSensorEditor({ device, onUpdated }: { device: Device; onUpdated: () => void }) {
  const [open, setOpen] = useState(false)
  const [values, setValues] = useState<Record<string, number>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  // Only show editable numeric sensors (skip power on/off)
  const editableSensors = device.sensors.filter(
    s => s.unit !== 'on/off' && typeof s.value === 'number' && SENSOR_RANGES[s.name]
  )

  useEffect(() => {
    const init: Record<string, number> = {}
    for (const s of editableSensors) {
      init[s.name] = typeof s.value === 'number' ? s.value : 0
    }
    setValues(init)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reinit on device change only; including editableSensors would loop
  }, [device.device_id])

  if (editableSensors.length === 0) return null

  const handleApply = async () => {
    setSaving(true)
    setSaved(false)
    try {
      await api.updateVirtualSensors(device.device_id, values)
      setSaved(true)
      onUpdated()
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mt-3 overflow-hidden rounded-2xl border border-violet-200/60 bg-violet-50/40">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center gap-2 px-3.5 py-2.5 text-xs font-semibold text-violet-600 transition-colors hover:bg-violet-50"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        <FlaskConical className="w-3.5 h-3.5" />
        <span>模拟传感器数据</span>
        <span className="ml-auto text-[10px] text-violet-400 font-normal">修改后触发 AI 响应</span>
      </button>

      {open && (
        <div className="px-3.5 pb-3.5 space-y-3">
          {editableSensors.map(s => {
            const range = SENSOR_RANGES[s.name]
            const val = values[s.name] ?? (typeof s.value === 'number' ? s.value : 0)
            return (
              <div key={s.name}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-slate-500">{SENSOR_LABELS[s.name] || s.name}</span>
                  <span className="text-xs font-mono font-semibold text-violet-700">{val}{s.unit}</span>
                </div>
                <input
                  type="range"
                  min={range.min}
                  max={range.max}
                  step={range.step}
                  value={val}
                  onChange={e => setValues(prev => ({ ...prev, [s.name]: Number(e.target.value) }))}
                  className="w-full"
                />
                <div className="flex justify-between text-[10px] text-slate-400 mt-0.5">
                  <span>{range.min}</span>
                  <span>{range.max}</span>
                </div>
              </div>
            )
          })}

          <button
            onClick={handleApply}
            disabled={saving}
            className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-xl bg-violet-600 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-violet-700 disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : saved ? <Check className="w-3.5 h-3.5" /> : <FlaskConical className="w-3.5 h-3.5" />}
            {saved ? '已推送，AI 正在响应...' : '推送传感器数据'}
          </button>
        </div>
      )}
    </div>
  )
}

function ActiveCard({ device, onDevicesChanged }: { device: Device; onDevicesChanged?: () => void }) {
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [values, setValues] = useState<CapabilityValueState>({})

  useEffect(() => {
    const nextValues: CapabilityValueState = {}
    for (const capability of device.capabilities) {
      const inputs = capability.params?.inputs || []
      if (inputs.length === 1) {
        const input = inputs[0]
        const currentValue = getCurrentCapabilityValue(device, capability, input)
        if (currentValue !== undefined) {
          nextValues[capability.name] = currentValue
        } else if (input.default !== undefined) {
          nextValues[capability.name] = input.default
        } else if (input.type === 'enum' && input.options?.length) {
          nextValues[capability.name] = input.options[0]
        } else if (input.type === 'number') {
          nextValues[capability.name] = getNumericRange(capability, input)?.min ?? 0
        } else {
          nextValues[capability.name] = ''
        }
      }
    }
    setValues(nextValues)
  }, [device])

  const handleCommand = async (action: string, params: Record<string, unknown> = {}) => {
    setBusyAction(action)
    setError('')
    setMessage('')
    try {
      const result = await api.sendCommand(device.device_id, action, params)
      if (result.success) {
        setMessage(`${labelForAction(action)} 已发送`)
        setValues(prev => ({ ...prev, [action]: getSubmittedCapabilityValue(action, params) ?? prev[action] }))
        onDevicesChanged?.()
      } else {
        setError(result.message || '执行失败')
      }
    } catch {
      setError('控制命令发送失败')
    } finally {
      setBusyAction(null)
    }
  }

  const renderCapability = (capability: DeviceCapability) => {
    const disabled = busyAction !== null
    const isBusy = busyAction === capability.name
    const inputs = capability.params?.inputs || []

    if (inputs.length === 0) {
      return (
        <button
          key={capability.name}
          onClick={() => handleCommand(capability.name)}
          disabled={disabled}
          className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 text-sm font-semibold text-slate-700 transition-all hover:border-slate-300 hover:bg-slate-50 hover:shadow-sm disabled:opacity-50"
        >
          {isBusy ? <Loader2 className="h-4 w-4 animate-spin text-violet-500" /> : <Power className="h-4 w-4 text-slate-400" />}
          {labelForCapability(capability)}
        </button>
      )
    }

    if (inputs.length === 1) {
      const input = inputs[0]
      const value = values[capability.name]

      return (
        <div key={capability.name} className="w-full rounded-2xl border border-slate-200/70 bg-slate-50/70 p-3.5">
          <div className="mb-2.5 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">{labelForCapability(capability)}</p>
              {capability.params?.help && <p className="mt-0.5 text-xs text-slate-400">{capability.params.help}</p>}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {renderInputControl(capability, capability.name, input, value, disabled, setValues)}
            <button
              onClick={() => handleCommand(capability.name, { [input.name]: normalizeInputValue(input, value) })}
              disabled={disabled || value === '' || value === undefined}
              className="inline-flex h-10 cursor-pointer items-center gap-1.5 rounded-xl bg-violet-600 px-3.5 text-sm font-semibold text-white transition-colors hover:bg-violet-700 disabled:opacity-50"
            >
              {isBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              应用
            </button>
          </div>
        </div>
      )
    }

    return null
  }

  return (
    <div className="rounded-[22px] border border-slate-200/70 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_rgba(15,23,42,0.05)] transition-shadow hover:shadow-[0_2px_4px_rgba(15,23,42,0.05),0_12px_30px_rgba(15,23,42,0.07)]">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-slate-800">{device.name}</h3>
          <p className="text-xs text-slate-400 mt-0.5">{device.ip || device.device_id}</p>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
          device.online
            ? 'border border-emerald-200 bg-emerald-50 text-emerald-700'
            : 'bg-slate-100 text-slate-400 border border-slate-200'
        }`}>
          {device.online ? '在线' : '离线'}
        </span>
      </div>

      {device.sensors.length > 0 && (
        <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
          {device.sensors.map((s) => (
            <SensorBadge key={s.name} name={s.name} value={s.value} unit={s.unit} />
          ))}
        </div>
      )}

      {getVisibleCapabilities(device).length > 0 ? (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2.5">
            {getVisibleCapabilities(device).map((capability) => renderCapability(capability))}
          </div>
          {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
          {message && <p className="text-xs text-emerald-600 mt-1">{message}</p>}
        </div>
      ) : (
        <p className="text-sm text-slate-400">当前没有可用控制能力。</p>
      )}

      {device.adapter === 'virtual' && (
        <VirtualSensorEditor device={device} onUpdated={() => onDevicesChanged?.()} />
      )}
    </div>
  )
}

function renderInputControl(
  capability: DeviceCapability,
  capabilityName: string,
  input: CapabilityInput,
  value: string | number | boolean | undefined,
  disabled: boolean,
  setValues: Dispatch<SetStateAction<CapabilityValueState>>,
) {
  if (input.type === 'enum') {
    return (
      <select
        value={String(value ?? '')}
        onChange={(e) => setValues((prev) => ({ ...prev, [capabilityName]: e.target.value }))}
        disabled={disabled}
        className="h-10 flex-1 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 transition-all focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
      >
        {(input.options || []).map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
    )
  }

  if (input.type === 'boolean') {
    return (
      <select
        value={String(value ?? false)}
        onChange={(e) => setValues((prev) => ({ ...prev, [capabilityName]: e.target.value === 'true' }))}
        disabled={disabled}
        className="h-10 flex-1 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 transition-all focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
      >
        <option value="true">开启</option>
        <option value="false">关闭</option>
      </select>
    )
  }

  if (input.type === 'number') {
    const range = getNumericRange(capability, input)
    if (range) {
      const numericValue = Number(value ?? range.min)
      return (
        <div className="flex-1">
          <div className="mb-1 flex items-center justify-between text-xs text-slate-500">
            <span>{range.min}</span>
            <span className="font-mono text-slate-700">{numericValue}{range.unit || ''}</span>
            <span>{range.max}</span>
          </div>
          <input
            type="range"
            min={range.min}
            max={range.max}
            step={range.step}
            value={numericValue}
            onChange={(e) => setValues((prev) => ({ ...prev, [capabilityName]: Number(e.target.value) }))}
            disabled={disabled}
            className="w-full accent-violet-500"
          />
        </div>
      )
    }

    return (
      <input
        type="number"
        value={String(value ?? '')}
        onChange={(e) => setValues((prev) => ({ ...prev, [capabilityName]: Number(e.target.value) }))}
        disabled={disabled}
        className="h-10 flex-1 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 transition-all focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
      />
    )
  }

  return (
    <input
      type="text"
      value={String(value ?? '')}
      onChange={(e) => setValues((prev) => ({ ...prev, [capabilityName]: e.target.value }))}
      disabled={disabled}
      className="h-10 flex-1 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 transition-all focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
    />
  )
}

function normalizeInputValue(input: CapabilityInput, value: string | number | boolean | undefined) {
  if (input.type === 'number') {
    return Number(value)
  }
  if (input.type === 'boolean') {
    return Boolean(value)
  }
  return value
}

function getSubmittedCapabilityValue(action: string, params: Record<string, unknown>) {
  const sensorNames = SENSOR_NAMES_BY_CAPABILITY[action] || []
  for (const name of sensorNames) {
    const value = normalizeCapabilityValue(params[name])
    if (value !== undefined) return value
  }
  const values = Object.values(params)
  return values.length === 1 ? normalizeCapabilityValue(values[0]) : undefined
}

function normalizeCapabilityValue(value: unknown): string | number | boolean | undefined {
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return value
  }
  return undefined
}

function getCurrentCapabilityValue(device: Device, capability: DeviceCapability, input: CapabilityInput) {
  const sensorValue = getCapabilitySensorValue(device, capability.name)
  if (sensorValue === undefined) return undefined

  if (input.type === 'number') {
    const numericValue = Number(sensorValue)
    if (!Number.isFinite(numericValue)) return undefined
    const range = getNumericRange(capability, input)
    if (!range) return numericValue
    return Math.min(range.max, Math.max(range.min, numericValue))
  }

  if (input.type === 'boolean') {
    if (typeof sensorValue === 'boolean') return sensorValue
    if (typeof sensorValue === 'string') return ['true', 'on', '1', '开'].includes(sensorValue.toLowerCase())
    if (typeof sensorValue === 'number') return sensorValue !== 0
    return undefined
  }

  if (input.type === 'enum') {
    const value = String(sensorValue)
    return input.options?.includes(value) ? value : undefined
  }

  return String(sensorValue)
}

function getCapabilitySensorValue(device: Device, capabilityName: string) {
  const sensorNames = SENSOR_NAMES_BY_CAPABILITY[capabilityName] || []
  for (const name of sensorNames) {
    const sensor = device.sensors.find((item) => normalizeSensorName(item.name) === name)
    if (sensor && sensor.value !== null && sensor.value !== undefined) {
      return sensor.value
    }
  }
  return undefined
}

function normalizeSensorName(name: string) {
  return name.trim().toLowerCase().replace(/[-\s]+/g, '_')
}

const SENSOR_NAMES_BY_CAPABILITY: Record<string, string[]> = {
  set_brightness: ['brightness'],
  set_color_temp: ['color_temp', 'color_temperature'],
  set_target_humidity: ['target_humidity', 'relative_humidity', 'humidity'],
  set_humidity: ['target_humidity', 'relative_humidity', 'humidity'],
  set_target_temperature: ['target_temperature', 'temperature'],
  set_temperature: ['target_temperature', 'temperature'],
  set_fan_level: ['fan_level', 'fan_speed'],
  set_mode: ['mode'],
}

function getNumericRange(capability: DeviceCapability, input: CapabilityInput) {
  const ranges: Record<string, { min: number; max: number; step: number; unit?: string }> = {
    'set_brightness:level': { min: 1, max: 100, step: 1, unit: '%' },
    'set_brightness:value': { min: 1, max: 100, step: 1, unit: '%' },
    'set_color_temp:level': { min: 2700, max: 6500, step: 100, unit: 'K' },
    'set_color_temp:kelvin': { min: 2700, max: 6500, step: 100, unit: 'K' },
    'set_color_temp:value': { min: 2700, max: 6500, step: 100, unit: 'K' },
    'set_target_humidity:humidity': { min: 30, max: 80, step: 1, unit: '%' },
    'set_target_humidity:value': { min: 30, max: 80, step: 1, unit: '%' },
    'set_target_temperature:target_temperature': { min: 16, max: 30, step: 1, unit: '°C' },
    'set_target_temperature:value': { min: 16, max: 30, step: 1, unit: '°C' },
    'set_fan_level:level': { min: 1, max: 2, step: 1 },
  }

  return ranges[`${capability.name}:${input.name}`] || null
}

function labelForCapability(capability: DeviceCapability) {
  return capability.params?.label || prettifyName(capability.name)
}

function getVisibleCapabilities(device: Device) {
  const preferredByType: Record<string, string[]> = {
    light: ['on', 'off', 'set_brightness', 'set_color_temp'],
    humidifier: ['on', 'off', 'set_target_humidity', 'set_mode'],
    dehumidifier: ['on', 'off', 'set_target_humidity', 'set_mode'],
    air_purifier: ['on', 'off', 'set_mode', 'set_fan_level'],
    speaker: ['play_random_audio', 'play_audio_file', 'play_audio_url', 'stop_audio'],
  }

  const preferred = preferredByType[device.type]
  if (!preferred) {
    return device.capabilities
  }

  const capabilityMap = new Map(device.capabilities.map((capability) => [capability.name, capability]))
  const filtered = preferred
    .map((name) => capabilityMap.get(name))
    .filter((capability): capability is DeviceCapability => Boolean(capability))

  return filtered.length > 0 ? filtered : device.capabilities
}

function labelForAction(action: string) {
  return prettifyName(action)
}

function prettifyName(name: string) {
  const aliases: Record<string, string> = {
    on: '开启',
    off: '关闭',
    play_random_audio: '随机播放一首',
    play_audio_file: '播放本地音频',
    play_audio_url: '播放音频 URL',
    stop_audio: '停止播放',
  }
  if (aliases[name]) {
    return aliases[name]
  }
  return name.replace(/^set_/, '').replace(/_/g, ' ')
}

export default function DeviceCard({ devices, selectedId, onDevicesChanged }: DeviceCardProps) {
  const selected = selectedId ? devices.find((d) => d.device_id === selectedId) : null
  const shown = selected ? [selected] : devices

  const sorted = [...shown].sort((a, b) => {
    if (a.needs_token === b.needs_token) return 0
    return a.needs_token ? 1 : -1
  })

  return (
    <div>
      {sorted.length === 0 ? (
        <div className="flex h-48 items-center justify-center text-slate-400">
          <div className="text-center">
            <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100">
              <Lightbulb className="h-7 w-7 text-slate-300" />
            </div>
            <p className="text-sm font-medium text-slate-500">暂无设备</p>
            <p className="mt-1 text-xs text-slate-400">点击右上角「扫描」发现局域网中的智能设备</p>
          </div>
        </div>
      ) : (
        <div className="grid gap-4">
          {sorted.map((device) =>
            device.needs_token ? (
              <NeedsTokenCard key={device.device_id} device={device} onActivated={onDevicesChanged || (() => {})} />
            ) : (
              <ActiveCard key={device.device_id} device={device} onDevicesChanged={onDevicesChanged} />
            ),
          )}
        </div>
      )}
    </div>
  )
}
