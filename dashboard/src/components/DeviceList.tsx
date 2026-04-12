import { useState, useRef, useEffect } from 'react'
import { Droplets, Thermometer, Lightbulb, Cpu, HelpCircle, Plus, Pencil, Trash2, ChevronDown, ChevronRight, Home } from 'lucide-react'
import { api } from '../hooks/useApi'
import type { Device, Room } from '../hooks/useApi'

const TYPE_ICONS: Record<string, typeof Cpu> = {
  humidifier: Droplets,
  air_conditioner: Thermometer,
  light: Lightbulb,
  air_purifier: Cpu,
}

const TYPE_LABELS: Record<string, string> = {
  humidifier: '加湿器',
  air_conditioner: '空调',
  light: '灯光',
  air_purifier: '净化器',
  vacuum: '扫地机',
  curtain: '窗帘',
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
        <div className="px-3 py-2 border-l-2 border-violet-500">
          <input
            ref={renameInputRef}
            value={renamingDeviceName}
            onChange={e => setRenamingDeviceName(e.target.value)}
            onBlur={() => handleRenameDevice(d.device_id)}
            onKeyDown={e => {
              if (e.key === 'Enter') handleRenameDevice(d.device_id)
              if (e.key === 'Escape') setRenamingDeviceId(null)
            }}
            className="w-full text-sm border border-violet-400 rounded-lg px-2 py-1 outline-none focus:ring-2 focus:ring-violet-500/20 bg-white"
          />
        </div>
      ) : (
        <button
          onClick={() => onSelect(d.device_id)}
          className={`w-full flex items-center gap-2.5 px-3 py-2.5 text-left transition-all cursor-grab active:cursor-grabbing ${
            selectedId === d.device_id
              ? 'bg-violet-50 border-l-2 border-violet-600 pl-[10px]'
              : 'border-l-2 border-transparent hover:bg-slate-50'
          }`}
        >
          <span className={`flex-shrink-0 ${d.needs_token ? 'text-amber-400' : d.online ? 'text-violet-600' : 'text-slate-300'}`}>
            <DeviceIcon type={d.type} />
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <p className={`text-sm font-medium truncate ${selectedId === d.device_id ? 'text-violet-700' : 'text-slate-700'}`}>{d.name}</p>
              {d.adapter === 'virtual' && (
                <span className="flex-shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-violet-100 text-violet-600 border border-violet-200">虚拟</span>
              )}
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">
              {d.needs_token ? '需要 Token' : (TYPE_LABELS[d.type] || d.type)} · {d.adapter}
            </p>
          </div>
          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${d.needs_token ? 'bg-amber-400' : d.online ? 'bg-emerald-400' : 'bg-slate-300'}`} />
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
        className={`transition-colors ${isOver ? 'bg-violet-50/60' : ''}`}
      >
        <div
          className="flex items-center gap-1 px-3 py-1.5 group"
          onContextMenu={(e) => openContextMenu(e, 'room', room.room_id, room.name)}
        >
          <button
            onClick={() => setCollapsed(c => ({ ...c, [room.room_id]: !isCollapsed }))}
            className="flex items-center gap-1 flex-1 min-w-0"
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
                className="text-[11px] font-semibold text-slate-600 bg-white border border-violet-400 rounded px-1 py-0.5 w-full outline-none"
              />
            ) : (
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest truncate">
                {room.name}
                <span className="ml-1 text-slate-300 normal-case font-normal">({roomDevices.length})</span>
              </span>
            )}
          </button>
          <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={() => { setEditingRoomId(room.room_id); setEditingName(room.name) }}
              className="p-1 text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded transition-colors"
            >
              <Pencil className="w-3 h-3" />
            </button>
            <button
              onClick={() => handleDeleteRoom(room.room_id)}
              className="p-1 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </div>
        </div>
        {!isCollapsed && (
          <ul>
            {roomDevices.length === 0 ? (
              <li className={`px-8 py-2 text-[11px] ${isOver ? 'text-violet-500' : 'text-slate-400'}`}>
                {isOver ? '松开以移入此房间' : '拖拽设备到此处'}
              </li>
            ) : roomDevices.map(renderDevice)}
          </ul>
        )}
      </div>
    )
  }

  return (
    <aside className="w-64 min-w-[256px] bg-white border-r border-slate-200/80 flex flex-col shadow-[1px_0_0_#e2e8f0]">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
        <h2 className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest">设备列表</h2>
        <button
          onClick={() => setAddingRoom(true)}
          className="p-1 text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded-md transition-colors"
          title="新增房间"
        >
          <Plus className="w-3.5 h-3.5" />
        </button>
      </div>

      {addingRoom && (
        <div className="px-3 py-2 border-b border-slate-100">
          <input
            ref={addInputRef}
            value={newRoomName}
            onChange={e => setNewRoomName(e.target.value)}
            onBlur={handleCreateRoom}
            onKeyDown={e => {
              if (e.key === 'Enter') handleCreateRoom()
              if (e.key === 'Escape') { setAddingRoom(false); setNewRoomName('') }
            }}
            placeholder="房间名称..."
            className="w-full text-sm border border-violet-300 rounded px-2 py-1 outline-none focus:ring-1 focus:ring-violet-400"
          />
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {devices.length === 0 ? (
          <div className="p-4 text-sm text-slate-400 text-center">
            <p>暂无设备</p>
            <p className="mt-1 text-xs">点击右上角「扫描设备」</p>
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
                  <div className="flex items-center gap-1 px-3 py-2">
                    <Home className="w-3.5 h-3.5 text-slate-300 flex-shrink-0" />
                    <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                      未分配
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

      <div className="px-4 py-2.5 border-t border-slate-100 text-[11px] text-slate-400 flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
        {devices.filter(d => d.online).length} 在线 · 共 {devices.length} 台
      </div>

      {/* Right-click context menu */}
      {contextMenu && (
        <div
          className="fixed z-50 min-w-[140px] rounded-xl border border-slate-200 bg-white shadow-lg py-1 text-sm"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={e => e.stopPropagation()}
        >
          <div className="px-3 py-1.5 text-[11px] text-slate-400 font-medium border-b border-slate-100 truncate max-w-[180px]">
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
                className="w-full flex items-center gap-2 px-3 py-2 text-slate-700 hover:bg-violet-50 hover:text-violet-700 transition-colors"
              >
                <Pencil className="w-3.5 h-3.5" />
                重命名
              </button>
              <button
                onClick={() => {
                  handleDeleteDevice(contextMenu.id)
                  setContextMenu(null)
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-red-500 hover:bg-red-50 transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                删除设备
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
                className="w-full flex items-center gap-2 px-3 py-2 text-slate-700 hover:bg-violet-50 hover:text-violet-700 transition-colors"
              >
                <Pencil className="w-3.5 h-3.5" />
                重命名房间
              </button>
              <button
                onClick={() => {
                  handleDeleteRoom(contextMenu.id)
                  setContextMenu(null)
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-red-500 hover:bg-red-50 transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                删除房间
              </button>
            </>
          )}
        </div>
      )}
    </aside>
  )
}
