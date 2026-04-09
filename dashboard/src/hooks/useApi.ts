import { useState, useEffect, useCallback } from 'react'

export interface CapabilityInput {
  name: string
  type: 'string' | 'number' | 'boolean' | 'enum'
  required?: boolean
  default?: string | number | boolean
  options?: string[]
}

export interface DeviceCapability {
  name: string
  params?: {
    label?: string
    help?: string
    inputs?: CapabilityInput[]
    [key: string]: unknown
  }
}

export interface Device {
  device_id: string
  name: string
  adapter: string
  type: string
  room: string | null
  online: boolean
  capabilities: DeviceCapability[]
  sensors: { name: string; unit: string; value: number | string | boolean | null }[]
  needs_token?: boolean
  ip?: string
}

export interface Decision {
  timestamp?: string
  device_id?: string
  device_type?: string
  action?: string
  params?: Record<string, unknown>
  reason?: string
  goal?: string
  message?: string
  task_kind?: string
  source?: string
}

export interface ChatTaskPlanItem {
  kind: string
  goal?: string
  reason?: string
  priority?: number
  skill_name?: string
  system_skill?: string
  system_action?: string
  question?: string
  params?: Record<string, unknown>
}

export interface ChatTaskResult {
  kind: string
  reason?: string
  reply?: string
  question?: string
  action?: string
  new_devices?: number
  total?: number
  refresh_result?: {
    refreshed: number
    failed: number
    environment?: EnvironmentSnapshot
  }
}

export interface ChatExecutionAction {
  skill_name: string
  device_id: string
  action: string
  params: Record<string, unknown>
  reason?: string
}

export interface ChatExecutionResult {
  plan_item: {
    skill_name: string
    device_type: string
    goal: string
    reason: string
    priority: number
  }
  actions: ChatExecutionAction[]
}

export interface EnvironmentSignalReading {
  device_id: string
  device_type: string
  room: string | null
  value: number | string | boolean | null
  unit: string
}

export interface EnvironmentDeviceSnapshot {
  device_id: string
  name: string
  type: string
  room: string | null
  online: boolean
  sensors: Record<string, { value: number | string | boolean | null; unit: string }>
}

export interface EnvironmentSnapshot {
  timestamp?: string
  current_device_id?: string | null
  current_device_type?: string | null
  devices: EnvironmentDeviceSnapshot[]
  signals: Record<string, EnvironmentSignalReading[]>
}

export interface RefreshEnvironmentResult {
  refreshed: number
  failed: number
  environment: EnvironmentSnapshot
}

export interface ScanResult {
  new_devices: number
  total: number
}

export interface ChatResponse {
  reply: string
  action?: string
  status?: string
  error?: string
  country?: string
  qr_image_b64?: string
  new_devices?: number
  total?: number
  refresh_devices?: boolean
  executed?: boolean
  task_plan_items?: ChatTaskPlanItem[]
  task_results?: ChatTaskResult[]
  execution_results?: ChatExecutionResult[]
}

export interface LearnedProfile {
  stable_preferences: string[]
  time_based_patterns: string[]
  seasonal_patterns: string[]
  weak_signals: string[]
  confidence_notes: string
  metadata?: Record<string, unknown>
}

export interface ExtractedMemory {
  topic: string
  title: string
  category: string
  summary: string
  details: string[]
  device_types: string[]
  confidence: 'low' | 'medium' | 'high'
  source_actions: string[]
  updated_at?: string
}

export interface MemoryManifestItem {
  topic: string
  title: string
  category: string
  summary: string
  updated_at?: string
}

export interface MemoryDebugSnapshot {
  preferences: string
  learned_profiles: Record<string, LearnedProfile>
  memory_manifest: MemoryManifestItem[]
  extracted_memories: Record<string, ExtractedMemory>
  extraction_state: {
    history_cursor: number
    last_extracted_at?: string
    last_batch_size?: number
  }
  recent_history: Decision[]
}

const api = {
  async getDevices(): Promise<Device[]> {
    const res = await fetch('/api/devices')
    return res.json()
  },

  async getDecisions(): Promise<Decision[]> {
    const res = await fetch('/api/decisions')
    return res.json()
  },

  async getEnvironment(): Promise<EnvironmentSnapshot> {
    const res = await fetch('/api/environment')
    return res.json()
  },

  async refreshEnvironment(): Promise<RefreshEnvironmentResult> {
    const res = await fetch('/api/environment/refresh', { method: 'POST' })
    return res.json()
  },

  async scan(): Promise<ScanResult> {
    const res = await fetch('/api/scan', { method: 'POST' })
    return res.json()
  },

  async sendCommand(deviceId: string, action: string, params: Record<string, unknown> = {}) {
    const res = await fetch(`/api/devices/${deviceId}/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: deviceId, action, params }),
    })
    return res.json()
  },

  async chat(message: string): Promise<ChatResponse> {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    })
    const text = await res.text()
    let data: ChatResponse | null = null
    try {
      data = JSON.parse(text) as ChatResponse
    } catch {
      /* non-json response */
    }

    if (!res.ok) {
      throw new Error(data?.reply || data?.error || `HTTP ${res.status}`)
    }

    if (!data) {
      throw new Error('后端返回了无效响应')
    }

    return data
  },

  async getHealth(): Promise<{ status: string; version: string }> {
    const res = await fetch('/health')
    return res.json()
  },

  async getMemory(): Promise<MemoryDebugSnapshot> {
    const res = await fetch('/api/memory')
    return res.json()
  },
}

export function useDevices(pollInterval = 5000) {
  const [devices, setDevices] = useState<Device[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const data = await api.getDevices()
      setDevices(data)
    } catch {
      /* backend may be starting */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, pollInterval)
    return () => clearInterval(id)
  }, [refresh, pollInterval])

  return { devices, loading, refresh }
}

export function useDecisions(pollInterval = 3000) {
  const [decisions, setDecisions] = useState<Decision[]>([])

  const refresh = useCallback(async () => {
    try {
      const data = await api.getDecisions()
      setDecisions(data)
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, pollInterval)
    return () => clearInterval(id)
  }, [refresh, pollInterval])

  return { decisions, refresh }
}

export function useEnvironment(pollInterval = 3000) {
  const [environment, setEnvironment] = useState<EnvironmentSnapshot | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const data = await api.getEnvironment()
      setEnvironment(data)
    } catch {
      /* ignore */
    }
  }, [])

  const refreshNow = useCallback(async () => {
    setRefreshing(true)
    try {
      const data = await api.refreshEnvironment()
      setEnvironment(data.environment)
      return data
    } finally {
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, pollInterval)
    return () => clearInterval(id)
  }, [refresh, pollInterval])

  return { environment, refresh, refreshNow, refreshing }
}

export function useMemoryDebug(pollInterval = 10000) {
  const [memory, setMemory] = useState<MemoryDebugSnapshot | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const data = await api.getMemory()
      setMemory(data)
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, pollInterval)
    return () => clearInterval(id)
  }, [refresh, pollInterval])

  return { memory, loading, refresh }
}

export { api }
