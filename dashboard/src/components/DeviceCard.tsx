import { useEffect, useState, type Dispatch, type SetStateAction } from 'react'
import { Droplets, Thermometer, Lightbulb, Zap, Power, Gauge, Key, Loader2, Check } from 'lucide-react'
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
  const display = value !== null && value !== undefined ? `${value}${unit}` : '--'

  return (
    <div className="flex items-center gap-2 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
      <Icon className="h-4 w-4 text-slate-400" />
      <div>
        <p className="text-xs capitalize text-slate-400">{name}</p>
        <p className="text-sm font-mono text-slate-700">{display}</p>
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
    <div className="rounded-xl border border-amber-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium text-slate-800">{device.name}</h3>
          <p className="text-sm text-slate-400">{device.ip || device.device_id}</p>
        </div>
        <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-600">
          需要激活
        </span>
      </div>

      <div className="mb-3 space-y-2 rounded-lg border border-amber-100 bg-amber-50 p-3 text-sm text-slate-600">
        <p className="font-medium text-slate-700">已在局域网发现此设备，但缺少 Token。</p>
        <ol className="ml-4 list-decimal space-y-1 text-slate-500">
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
              className="flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-mono focus:border-violet-400 focus:outline-none"
            />
            <button
              onClick={handleActivate}
              disabled={activating || !token}
              className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-violet-500 px-3 py-2 text-sm text-white transition-colors hover:bg-violet-600 disabled:opacity-40"
            >
              {activating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Key className="h-4 w-4" />}
              激活
            </button>
          </div>
          <button onClick={() => setShowTokenInput(false)} className="cursor-pointer text-xs text-slate-400 hover:text-slate-500">收起</button>
        </div>
      ) : (
        <button onClick={() => setShowTokenInput(true)} className="cursor-pointer text-sm text-violet-500 hover:text-violet-600">
          输入 Token
        </button>
      )}
      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
      {success && <p className="mt-2 flex items-center gap-1 text-sm text-emerald-600"><Check className="h-4 w-4" />{success}</p>}
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
        if (input.default !== undefined) {
          nextValues[capability.name] = input.default
        } else if (input.type === 'enum' && input.options?.length) {
          nextValues[capability.name] = input.options[0]
        } else if (input.type === 'number') {
          nextValues[capability.name] = 0
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
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50"
        >
          {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Power className="h-4 w-4" />}
          {labelForCapability(capability)}
        </button>
      )
    }

    if (inputs.length === 1) {
      const input = inputs[0]
      const value = values[capability.name]

      return (
        <div key={capability.name} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{labelForCapability(capability)}</p>
              {capability.params?.help && <p className="mt-1 text-xs text-slate-400">{capability.params.help}</p>}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {renderInputControl(capability, capability.name, input, value, disabled, setValues)}
            <button
              onClick={() => handleCommand(capability.name, { [input.name]: normalizeInputValue(input, value) })}
              disabled={disabled || value === '' || value === undefined}
              className="inline-flex items-center gap-2 rounded-lg bg-violet-500 px-3 py-2 text-sm text-white transition-colors hover:bg-violet-600 disabled:opacity-50"
            >
              {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              应用
            </button>
          </div>
        </div>
      )
    }

    return null
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium text-slate-800">{device.name}</h3>
          <p className="text-sm text-slate-400">{device.ip || device.device_id}</p>
        </div>
        <span className={`rounded-full px-2 py-1 text-xs ${
          device.online ? 'border border-emerald-200 bg-emerald-50 text-emerald-600' : 'bg-slate-100 text-slate-400'
        }`}>
          {device.online ? '在线' : '离线'}
        </span>
      </div>

      {device.sensors.length > 0 && (
        <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {device.sensors.map((s) => (
            <SensorBadge key={s.name} name={s.name} value={s.value} unit={s.unit} />
          ))}
        </div>
      )}

      {getVisibleCapabilities(device).length > 0 ? (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {getVisibleCapabilities(device).map((capability) => renderCapability(capability))}
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
          {message && <p className="text-sm text-emerald-600">{message}</p>}
        </div>
      ) : (
        <p className="text-sm text-slate-400">当前没有可用控制能力。</p>
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
        className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-violet-400 focus:outline-none"
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
        className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-violet-400 focus:outline-none"
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
        className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-violet-400 focus:outline-none"
      />
    )
  }

  return (
    <input
      type="text"
      value={String(value ?? '')}
      onChange={(e) => setValues((prev) => ({ ...prev, [capabilityName]: e.target.value }))}
      disabled={disabled}
      className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-violet-400 focus:outline-none"
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

function getNumericRange(capability: DeviceCapability, input: CapabilityInput) {
  const ranges: Record<string, { min: number; max: number; step: number; unit?: string }> = {
    'set_brightness:level': { min: 1, max: 100, step: 1, unit: '%' },
    'set_color_temp:level': { min: 2700, max: 6500, step: 100, unit: 'K' },
    'set_target_humidity:humidity': { min: 30, max: 80, step: 1, unit: '%' },
    'set_target_temperature:target_temperature': { min: 16, max: 30, step: 1, unit: '°C' },
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
        <div className="flex h-full items-center justify-center text-slate-400">
          <div className="text-center">
            <Lightbulb className="mx-auto mb-3 h-12 w-12 opacity-30" />
            <p>暂无设备</p>
            <p className="mt-1 text-sm">点击右上角「扫描设备」发现局域网中的智能设备</p>
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
