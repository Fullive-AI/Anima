import { useState, useEffect, useCallback } from 'react'

export interface Device {
  device_id: string
  name: string
  adapter: string
  type: string
  room: string | null
  online: boolean
  capabilities: { name: string; params?: Record<string, unknown> }[]
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
    return res.json()
  },

  async getHealth(): Promise<{ status: string; version: string }> {
    const res = await fetch('/health')
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

export { api }
