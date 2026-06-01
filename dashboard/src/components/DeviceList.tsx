import { useState, useRef, useEffect } from 'react'
import { Droplets, Thermometer, Lightbulb, Cpu, HelpCircle, Plus, Pencil, Trash2, ChevronDown, ChevronRight, Home } from 'lucide-react'
import { api } from '../hooks/useApi'
import type { Device, Room } from '../hooks/useApi'
import { useI18n } from '../i18n/useI18n'

const TYPE_ICONS: Record<string, typeof Cpu> = {
  humidifier: Droplets,
  air_conditioner: Thermometer,
  light: Lightbulb,
  air_purifier: Cpu,
}

interface DeviceListProps {
  devices: Device[]
  selectedId: string | null
  onSelect: (id: string) => void
  onDevicesChanged: () => void
}

interface ContextMenu {
  x: number
  y: number
  type: 'device' | 'room'
  id: string
  name: string
}

function DeviceIcon({ type }: { type: string }) {
  const Comp = TYPE_ICONS[type] || HelpCircle
  return <Comp className="w-5 h-5" />
}

export default function DeviceList({ devices, selectedId, onSelect, onDevicesChanged }: DeviceListProps) {
  const { t } = useI18n()
  const [rooms, setRooms] = useState<Room[]>([])
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const [editingRoomId, setEditingRoomId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')
  const [addingRoom, setAddingRoom] = useState(false)
  const [newRoomName, setNewRoomName] = useState('')
  const [dragDeviceId, setDragDeviceId] = useState<string | null>(null)
  const [dragOverRoomId, setDragOverRoomId] = useState<string | null>(null)
  const [contextMenu, setContextMenu] = useState<ContextMenu | null>(null)
  const [renamingDeviceId, setRenamingDeviceId] = useState<string | null>(null)
  const [renamingDeviceName, setRenamingDeviceName] = useState('')
  const renameInputRef = useRef<HTMLInputElement>(null)
  const editInputRef = useRef<HTMLInputElement>(null)
  const addInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.getRooms().then(setRooms).catch(() => {})
  }, [])

  useEffect(() => {
    if (editingRoomId && editInputRef.current) editInputRef.current.focus()
  }, [editingRoomId])

  useEffect(() => {
    if (addingRoom && addInputRef.current) addInputRef.current.focus()
  }, [addingRoom])

  useEffect(() => {
    if (renamingDeviceId && renameInputRef.current) renameInputRef.current.focus()
  }, [renamingDeviceId])

  // Close context menu on outside click
  useEffect(() => {
    if (!contextMenu) return
    const handler = () => setContextMenu(null)
    window.addEventListener('click', handler)
    return () => window.removeEventListener('click', handler)
  }, [contextMenu])

  const handleCreateRoom = async () => {
    const name = newRoomName.trim()
    if (!name) { setAddingRoom(false); return }
    const room = await api.createRoom(name)
    setRooms(r => [...r, room])
    setNewRoomName('')
    setAddingRoom(false)
  }

  const handleRenameRoom = async (roomId: string) => {
    const name = editingName.trim()
    if (!name) { setEditingRoomId(null); return }
    const updated = await api.renameRoom(roomId, name)
    setRooms(r => r.map(x => x.room_id === roomId ? updated : x))
    setEditingRoomId(null)
  }

  const handleDeleteRoom = async (roomId: string) => {
    // Migrate devices in this room to unassigned first
    const roomDeviceList = devices.filter(d => d.room === roomId)
    await Promise.all(roomDeviceList.map(d => api.setDeviceRoom(d.device_id, null)))
    await api.deleteRoom(roomId)
    setRooms(r => r.filter(x => x.room_id !== roomId))
    onDevicesChanged()
  }

  const handleRenameDevice = async (deviceId: string) => {
    const name = renamingDeviceName.trim()
    if (!name) { setRenamingDeviceId(null); return }
    await fetch(`/api/devices/${deviceId}/rename`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    setRenamingDeviceId(null)
    onDevicesChanged()
  }

  const handleDeleteDevice = async (deviceId: string) => {
    await fetch(`/api/devices/${deviceId}`, { method: 'DELETE' })
    onDevicesChanged()
  }

  const handleDrop = async (roomId: string | null) => {
    if (!dragDeviceId) return
    await api.setDeviceRoom(dragDeviceId, roomId)
    onDevicesChanged()
    setDragDeviceId(null)
    setDragOverRoomId(null)
  }

  const openContextMenu = (e: React.MouseEvent, type: 'device' | 'room', id: string, name: string) => {
    e.preventDefault()
    e.stopPropagation()
    setContextMenu({ x: e.clientX, y: e.clientY, type, id, name })
  }

  // Group devices
  const roomedDevices: Record<string, Device[]> = {}
  const unassigned: Device[] = []
  for (const d of devices) {
    if (d.room) {
      roomedDevices[d.room] = [...(roomedDevices[d.room] || []), d]
    } else {
      unassigned.push(d)
    }
  }

  const renderDevice = (d: Device) => (
    <li
      key={d.device_id}
      draggable
      onDragStart={() => setDragDeviceId(d.device_id)}
      onDragEnd={() => { setDragDeviceId(null); setDragOverRoomId(null) }}
      onContextMenu={(e) => openContextMenu(e, 'device', d.device_id, d.name)}
    >
      {renamingDeviceId === d.device_id ? (
        <div className="mx-2 rounded-xl border border-violet-200 bg-violet-50/60 px-3 py-2">
          <input
            ref={renameInputRef}
            value={renamingDeviceName}
            onChange={e => setRenamingDeviceName(e.target.value)}
            onBlur={() => handleRenameDevice(d.device_id)}
            onKeyDown={e => {
              if (e.key === 'Enter') handleRenameDevice(d.device_id)
              if (e.key === 'Escape') setRenamingDeviceId(null)
            }}
            className="w-full rounded-lg border border-violet-300 bg-white px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-violet-500/20"
          />
        </div>
      ) : (
        <button
          onClick={() => onSelect(d.device_id)}
          className={`mx-2 flex w-[calc(100%-1rem)] cursor-grab items-center gap-2.5 rounded-xl px-3 py-2.5 text-left transition-all active:cursor-grabbing ${
            selectedId === d.device_id
              ? 'bg-violet-50 text-violet-700 shadow-[inset_3px_0_0_#7c3aed,0_1px_2px_rgba(124,58,237,0.08)]'
              : 'text-slate-700 hover:bg-slate-50'
          }`}
        >
          <span className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg ${
            selectedId === d.device_id ? 'bg-white text-violet-600 shadow-sm' : d.needs_token ? 'bg-amber-50 text-amber-500' : d.online ? 'bg-violet-50 text-violet-600' : 'bg-slate-100 text-slate-300'
          }`}>
            <DeviceIcon type={d.type} />
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <p className={`truncate text-sm font-semibold ${selectedId === d.device_id ? 'text-violet-700' : 'text-slate-700'}`}>{d.name}</p>
              {d.adapter === 'virtual' && (
                <span className="flex-shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-violet-100 text-violet-600 border border-violet-200">{t('deviceList.virtual')}</span>
              )}
            </div>
            <p className="mt-0.5 truncate text-[11px] text-slate-400">
              {d.needs_token ? t('deviceList.needsToken') : t(`deviceTypes.${d.type}`, undefined, d.type)} · {d.adapter}
            </p>
          </div>
          <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${d.needs_token ? 'bg-amber-400' : d.online ? 'bg-emerald-400' : 'bg-slate-300'}`} />
        </button>
      )}
    </li>
  )

  const renderRoomSection = (room: Room) => {
    const isCollapsed = collapsed[room.room_id]
    const roomDevices = roomedDevices[room.room_id] || []
    const isOver = dragOverRoomId === room.room_id

    return (
      <div
        key={room.room_id}
        onDragOver={e => { e.preventDefault(); setDragOverRoomId(room.room_id) }}
        onDragLeave={() => setDragOverRoomId(null)}
        onDrop={() => handleDrop(room.room_id)}
        className={`py-1 transition-colors ${isOver ? 'bg-violet-50/60' : ''}`}
      >
        <div
          className="group mx-2 flex items-center gap-1 rounded-lg px-2 py-1.5"
          onContextMenu={(e) => openContextMenu(e, 'room', room.room_id, room.name)}
        >
          <button
            onClick={() => setCollapsed(c => ({ ...c, [room.room_id]: !isCollapsed }))}
            className="flex min-w-0 flex-1 items-center gap-1"
          >
            {isCollapsed
              ? <ChevronRight className="w-3 h-3 text-slate-400 flex-shrink-0" />
              : <ChevronDown className="w-3 h-3 text-slate-400 flex-shrink-0" />
            }
            {editingRoomId === room.room_id ? (
              <input
                ref={editInputRef}
                value={editingName}
                onChange={e => setEditingName(e.target.value)}
                onBlur={() => handleRenameRoom(room.room_id)}
                onKeyDown={e => {
                  if (e.key === 'Enter') handleRenameRoom(room.room_id)
                  if (e.key === 'Escape') setEditingRoomId(null)
                }}
                onClick={e => e.stopPropagation()}
                className="w-full rounded border border-violet-300 bg-white px-1 py-0.5 text-[11px] font-semibold text-slate-600 outline-none"
              />
            ) : (
              <span className="truncate text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                {room.name}
                <span className="ml-1 text-slate-300 normal-case font-normal">({roomDevices.length})</span>
              </span>
            )}
          </button>
          <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
            <button
              onClick={() => { setEditingRoomId(room.room_id); setEditingName(room.name) }}
              className="rounded-md p-1 text-slate-400 transition-colors hover:bg-violet-50 hover:text-violet-600"
            >
              <Pencil className="w-3 h-3" />
            </button>
            <button
              onClick={() => handleDeleteRoom(room.room_id)}
              className="rounded-md p-1 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-500"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </div>
        </div>
        {!isCollapsed && (
          <ul>
            {roomDevices.length === 0 ? (
              <li className={`mx-2 rounded-lg px-8 py-2 text-[11px] ${isOver ? 'bg-violet-50 text-violet-500' : 'text-slate-400'}`}>
                {isOver ? t('deviceList.dropActive') : t('deviceList.dropHint')}
              </li>
            ) : roomDevices.map(renderDevice)}
          </ul>
        )}
      </div>
    )
  }

  return (
    <aside className="flex w-[328px] min-w-[328px] flex-col overflow-hidden rounded-[24px] border border-slate-200/70 bg-white/95 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_rgba(15,23,42,0.05)]">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">{t('deviceList.title')}</h2>
        <button
          onClick={() => setAddingRoom(true)}
          className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-violet-50 hover:text-violet-600"
          title={t('deviceList.addRoom')}
        >
          <Plus className="w-3.5 h-3.5" />
        </button>
      </div>

      {addingRoom && (
        <div className="border-b border-slate-100 px-3 py-2">
          <input
            ref={addInputRef}
            value={newRoomName}
            onChange={e => setNewRoomName(e.target.value)}
            onBlur={handleCreateRoom}
            onKeyDown={e => {
              if (e.key === 'Enter') handleCreateRoom()
              if (e.key === 'Escape') { setAddingRoom(false); setNewRoomName('') }
            }}
            placeholder={t('deviceList.roomNamePlaceholder')}
            className="w-full rounded-lg border border-violet-300 px-2.5 py-1.5 text-sm outline-none focus:ring-2 focus:ring-violet-500/20"
          />
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {devices.length === 0 ? (
          <div className="p-5 text-center text-sm text-slate-400">
            <p>{t('deviceList.emptyTitle')}</p>
            <p className="mt-1 text-xs">{t('deviceList.emptyHint')}</p>
          </div>
        ) : (
          <>
            {rooms.map(renderRoomSection)}

            {unassigned.length > 0 && (
              <div
                onDragOver={e => { e.preventDefault(); setDragOverRoomId('__unassigned__') }}
                onDragLeave={() => setDragOverRoomId(null)}
                onDrop={() => handleDrop(null)}
                className={`transition-colors ${dragOverRoomId === '__unassigned__' ? 'bg-slate-50' : ''}`}
              >
                {rooms.length > 0 && (
                  <div className="mx-2 flex items-center gap-1 rounded-lg px-2 py-2">
                    <Home className="w-3.5 h-3.5 text-slate-300 flex-shrink-0" />
                    <span className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                      {t('deviceList.unassigned')}
                      <span className="ml-1 text-slate-300 normal-case">({unassigned.length})</span>
                    </span>
                  </div>
                )}
                <ul>{unassigned.map(renderDevice)}</ul>
              </div>
            )}
          </>
        )}
      </div>

      <div className="flex items-center gap-1.5 border-t border-slate-100 bg-white/90 px-4 py-2.5 text-[11px] text-slate-400">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
        {t('deviceList.footerStats', { online: devices.filter(d => d.online).length, total: devices.length })}
      </div>

      {/* Right-click context menu */}
      {contextMenu && (
        <div
          className="fixed z-50 min-w-[148px] rounded-xl border border-slate-200 bg-white py-1 text-sm shadow-[0_16px_40px_rgba(15,23,42,0.14)]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={e => e.stopPropagation()}
        >
          <div className="max-w-[180px] truncate border-b border-slate-100 px-3 py-1.5 text-[11px] font-medium text-slate-400">
            {contextMenu.name}
          </div>
          {contextMenu.type === 'device' && (
            <>
              <button
                onClick={() => {
                  setRenamingDeviceId(contextMenu.id)
                  setRenamingDeviceName(contextMenu.name)
                  setContextMenu(null)
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-slate-700 transition-colors hover:bg-violet-50 hover:text-violet-700"
              >
                <Pencil className="w-3.5 h-3.5" />
                {t('deviceList.rename')}
              </button>
              <button
                onClick={() => {
                  handleDeleteDevice(contextMenu.id)
                  setContextMenu(null)
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-red-500 transition-colors hover:bg-red-50"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {t('deviceList.deleteDevice')}
              </button>
            </>
          )}
          {contextMenu.type === 'room' && (
            <>
              <button
                onClick={() => {
                  setEditingRoomId(contextMenu.id)
                  setEditingName(contextMenu.name)
                  setContextMenu(null)
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-slate-700 transition-colors hover:bg-violet-50 hover:text-violet-700"
              >
                <Pencil className="w-3.5 h-3.5" />
                {t('deviceList.renameRoom')}
              </button>
              <button
                onClick={() => {
                  handleDeleteRoom(contextMenu.id)
                  setContextMenu(null)
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-red-500 transition-colors hover:bg-red-50"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {t('deviceList.deleteRoom')}
              </button>
            </>
          )}
        </div>
      )}
    </aside>
  )
}
