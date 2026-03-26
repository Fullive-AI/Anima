import { useState } from 'react'
import Header from './components/Header'
import DeviceList from './components/DeviceList'
import DeviceCard from './components/DeviceCard'
import DecisionLog from './components/DecisionLog'
import EnvironmentPanel from './components/EnvironmentPanel'
import ChatBar from './components/ChatBar'
import SettingsPanel from './components/SettingsPanel'
import HelpPanel from './components/HelpPanel'
import StartupOnboardingModal from './components/StartupOnboardingModal'
import { useDevices, useDecisions, useEnvironment } from './hooks/useApi'

export default function App() {
  const { devices, refresh } = useDevices()
  const { decisions } = useDecisions()
  const { environment, refreshNow: refreshEnvironmentNow, refreshing: refreshingEnvironment } = useEnvironment()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)

  const handleRefreshEnvironment = async () => {
    await refreshEnvironmentNow()
    await refresh()
  }

  return (
    <div className="h-screen flex flex-col bg-slate-50">
      <Header
        deviceCount={devices.length}
        onScan={refresh}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenHelp={() => setHelpOpen(true)}
      />

      <div className="flex flex-1 overflow-hidden">
        <DeviceList
          devices={devices}
          selectedId={selectedId}
          onSelect={(id) => setSelectedId(id === selectedId ? null : id)}
        />
        <main className="flex-1 overflow-y-auto bg-slate-50 p-5">
          <div className="grid gap-4">
            <EnvironmentPanel
              environment={environment}
              refreshing={refreshingEnvironment}
              onRefresh={handleRefreshEnvironment}
            />
            <DeviceCard devices={devices} selectedId={selectedId} onDevicesChanged={refresh} />
          </div>
        </main>
        <DecisionLog decisions={decisions} />
      </div>

      <ChatBar onDevicesChanged={refresh} />
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
    </div>
  )
}
