import { useState, useRef } from 'react'
import Header from './components/Header'
import DeviceList from './components/DeviceList'
import DeviceCard from './components/DeviceCard'
import DecisionLog from './components/DecisionLog'
import EnvironmentPanel from './components/EnvironmentPanel'
import SettingsPanel from './components/SettingsPanel'
import HelpPanel from './components/HelpPanel'
import StartupOnboardingModal from './components/StartupOnboardingModal'
import MemoryPanel from './components/MemoryPanel'
import SkillsPanel from './components/SkillsPanel'
import VoiceOrb from './components/VoiceOrb'
import { useDevices, useEnvironment } from './hooks/useApi'

export default function App() {
  const { devices, refresh } = useDevices()
  const { environment, refreshNow: refreshEnvironmentNow, refreshing: refreshingEnvironment } = useEnvironment()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const [memoryOpen, setMemoryOpen] = useState(false)
  const [skillsOpen, setSkillsOpen] = useState(false)
  const sendMessageRef = useRef<((text: string) => void) | null>(null)

  const handleRefreshEnvironment = async () => {
    await refreshEnvironmentNow()
    await refresh()
  }

  const handleVoiceSend = (text: string) => {
    sendMessageRef.current?.(text)
  }

  return (
    <div className="flex h-screen flex-col bg-[var(--color-bg)]">
      <Header
        deviceCount={devices.length}
        onScan={refresh}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenHelp={() => setHelpOpen(true)}
        onOpenMemory={() => setMemoryOpen(true)}
        onOpenSkills={() => setSkillsOpen(true)}
      />

      <div className="flex flex-1 gap-3 overflow-hidden px-3 py-4">
        <DeviceList
          devices={devices}
          selectedId={selectedId}
          onSelect={(id) => setSelectedId(id === selectedId ? null : id)}
          onDevicesChanged={refresh}
        />
        <main className="flex-1 overflow-y-auto py-5 pl-8 pr-4 pb-28">
          <div className="mx-auto grid w-full max-w-none gap-5">
            <EnvironmentPanel
              environment={environment}
              refreshing={refreshingEnvironment}
              onRefresh={handleRefreshEnvironment}
            />
            <DeviceCard devices={devices} selectedId={selectedId} onDevicesChanged={refresh} />
          </div>
        </main>
        <DecisionLog
          onDevicesChanged={refresh}
          sendMessageRef={sendMessageRef}
        />
      </div>

      <VoiceOrb onSend={handleVoiceSend} />

      <StartupOnboardingModal onDevicesChanged={refresh} />

      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onDevicesChanged={refresh}
      />
      <HelpPanel
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
      />
      <MemoryPanel
        open={memoryOpen}
        onClose={() => setMemoryOpen(false)}
      />
      <SkillsPanel
        open={skillsOpen}
        onClose={() => setSkillsOpen(false)}
      />
    </div>
  )
}
