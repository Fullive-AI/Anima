import { CloudSun, Droplets, Gauge, Lightbulb, Loader2, RefreshCw, Thermometer, Waves, Zap } from 'lucide-react'
import type { EnvironmentSnapshot } from '../hooks/useApi'

interface EnvironmentPanelProps {
  environment: EnvironmentSnapshot | null
  refreshing?: boolean
  onRefresh?: () => void | Promise<void>
}

const SIGNAL_META: Record<string, { label: string; icon: typeof Gauge; unitFallback?: string }> = {
  temperature: { label: '温度', icon: Thermometer, unitFallback: '°C' },
  humidity: { label: '湿度', icon: Droplets, unitFallback: '%' },
  brightness: { label: '亮度', icon: Lightbulb, unitFallback: '%' },
  color_temp: { label: '色温', icon: Zap, unitFallback: 'K' },
  water_level: { label: '水位', icon: Waves, unitFallback: '%' },
}

const DEVICE_STATE_SIGNALS = new Set(['power', 'brightness', 'color_temp', 'water_level'])

function summarizeSignal(values: EnvironmentSnapshot['signals'][string] | undefined) {
  if (!values || values.length === 0) {
    return null
  }

  const numeric = values
    .map((item) => typeof item.value === 'number' ? item.value : Number.NaN)
    .filter((value) => Number.isFinite(value))

  const unit = values[0]?.unit || ''
  if (numeric.length > 0) {
    const avg = numeric.reduce((sum, value) => sum + value, 0) / numeric.length
    const rounded = avg >= 100 ? Math.round(avg) : Math.round(avg * 10) / 10
    return { value: String(rounded), unit, samples: values.length }
  }

  const first = values.find((item) => item.value !== null && item.value !== undefined)
  if (!first) {
    return null
  }

  return { value: String(first.value), unit: unit || '', samples: values.length }
}

function formatTime(timestamp?: string) {
  if (!timestamp) return '--'
  try {
    return new Date(timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return '--'
  }
}

export default function EnvironmentPanel({ environment, refreshing = false, onRefresh }: EnvironmentPanelProps) {
  const signals = environment?.signals || {}
  const featured = ['temperature', 'humidity']
    .map((name) => ({ name, summary: summarizeSignal(signals[name]) }))
    .filter((item) => item.summary)
  const deviceSignals = Object.entries(signals)
    .filter(([name]) => DEVICE_STATE_SIGNALS.has(name))
    .map(([name, values]) => ({ name, summary: summarizeSignal(values) }))
    .filter((item) => item.summary)

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-amber-50 p-2 text-amber-500">
            <CloudSun className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-sm font-medium uppercase tracking-wider text-slate-500">当前环境</h2>
            <p className="mt-1 text-sm text-slate-400">聚合当前空间内已上报的关键传感器状态</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-slate-400">{formatTime(environment?.timestamp)}</span>
          <button
            onClick={() => void onRefresh?.()}
            disabled={refreshing}
            className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-50 disabled:cursor-default disabled:opacity-50"
          >
            {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            刷新状态
          </button>
        </div>
      </div>

      {!environment || environment.devices.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-400">
          暂无环境快照，等待设备上报传感器数据
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {featured.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-xs text-slate-400 md:col-span-2 xl:col-span-4">
                当前没有可聚合的温度、湿度类环境信号
              </div>
            ) : (
              featured.map(({ name, summary }) => {
                const meta = SIGNAL_META[name] || { label: name, icon: Gauge }
                const Icon = meta.icon
                return (
                  <div key={name} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5">
                    <div className="mb-1.5 flex items-center justify-between">
                      <div className="flex items-center gap-2 text-slate-500">
                        <Icon className="h-3.5 w-3.5" />
                        <span className="text-xs">{meta.label}</span>
                      </div>
                      <span className="text-xs text-slate-400">{summary?.samples} 源</span>
                    </div>
                    <div className="text-xl font-semibold text-slate-800">
                      {summary?.value}
                      <span className="ml-1 text-xs font-normal text-slate-400">{summary?.unit || meta.unitFallback || ''}</span>
                    </div>
                  </div>
                )
              })
            )}
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-700">设备自身状态</p>
                <p className="mt-1 text-xs text-slate-400">这些值描述设备当前工作状态，不等同于环境信号</p>
              </div>
            </div>
            {deviceSignals.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 bg-white px-4 py-5 text-xs text-slate-400">
                当前没有可展示的设备状态
              </div>
            ) : (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {deviceSignals.map(({ name, summary }) => {
                  const meta = SIGNAL_META[name] || { label: name, icon: Gauge }
                  const Icon = meta.icon
                  return (
                    <div key={name} className="rounded-xl border border-white bg-white px-3 py-2.5">
                      <div className="mb-1.5 flex items-center justify-between">
                        <div className="flex items-center gap-2 text-slate-500">
                          <Icon className="h-3.5 w-3.5" />
                          <span className="text-xs">{meta.label}</span>
                        </div>
                        <span className="text-xs text-slate-400">{summary?.samples} 源</span>
                      </div>
                      <div className="text-xl font-semibold text-slate-800">
                        {summary?.value}
                        <span className="ml-1 text-xs font-normal text-slate-400">{summary?.unit || meta.unitFallback || ''}</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
