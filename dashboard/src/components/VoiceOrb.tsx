import { useState, useRef, useCallback } from 'react'
import { Mic, MicOff, X } from 'lucide-react'

interface VoiceOrbProps {
  onSend: (text: string, isVoice: boolean) => void
  disabled?: boolean
}

interface SpeechRecognitionEvent extends Event {
  resultIndex: number
  results: SpeechRecognitionResultList
}

interface SpeechRecognitionInstance extends EventTarget {
  lang: string
  continuous: boolean
  interimResults: boolean
  onstart: (() => void) | null
  onresult: ((e: SpeechRecognitionEvent) => void) | null
  onerror: (() => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
}

declare global {
  interface Window {
    webkitSpeechRecognition: new () => SpeechRecognitionInstance
    SpeechRecognition: new () => SpeechRecognitionInstance
  }
}

export default function VoiceOrb({ onSend, disabled }: VoiceOrbProps) {
  const [listening, setListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [supported] = useState(() => {
    if (typeof window === 'undefined') return true
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition)
  })
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null)
  const silenceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastFinalRef = useRef('')

  const clearSilenceTimer = () => {
    if (silenceTimer.current) {
      clearTimeout(silenceTimer.current)
      silenceTimer.current = null
    }
  }

  const stopListening = useCallback(() => {
    clearSilenceTimer()
    recognitionRef.current?.stop()
    recognitionRef.current = null
    setListening(false)
  }, [])

  const sendText = useCallback((text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    stopListening()
    setTranscript('')
    lastFinalRef.current = ''
    onSend(`[语音输入] ${trimmed}`, true)
  }, [onSend, stopListening])

  const startListening = useCallback(() => {
    if (disabled) return
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return

    const recognition = new SR()
    recognition.lang = 'zh-CN'
    recognition.continuous = true
    recognition.interimResults = true
    recognitionRef.current = recognition

    recognition.onstart = () => setListening(true)

    recognition.onresult = (e) => {
      let interim = ''
      let final = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const result = e.results[i]
        if (result.isFinal) {
          final += result[0].transcript
        } else {
          interim += result[0].transcript
        }
      }
      if (final) {
        lastFinalRef.current += final
      }
      setTranscript(lastFinalRef.current + interim)

      // Reset silence timer on any speech
      clearSilenceTimer()
      silenceTimer.current = setTimeout(() => {
        const text = lastFinalRef.current || interim
        if (text.trim()) sendText(text)
        else stopListening()
      }, 2000)
    }

    recognition.onerror = () => stopListening()
    recognition.onend = () => {
      // If still listening (not manually stopped), restart for continuous mode
      if (recognitionRef.current) {
        try { recognition.start() } catch { stopListening() }
      } else {
        setListening(false)
      }
    }

    recognition.start()
  }, [disabled, sendText, stopListening])

  const handleClick = () => {
    if (listening) {
      const text = lastFinalRef.current || transcript
      if (text.trim()) sendText(text)
      else stopListening()
    } else {
      startListening()
    }
  }

  if (!supported) return null

  return (
    <div className="pointer-events-none fixed bottom-7 left-1/2 z-40 flex -translate-x-1/2 flex-col items-center gap-3">
      {/* Transcript bubble */}
      {listening && (
        <div className="pointer-events-auto flex w-max max-w-xs items-center gap-2 rounded-2xl border border-slate-200 bg-white/95 px-4 py-2.5 shadow-[0_12px_30px_rgba(15,23,42,0.12)] backdrop-blur-sm">
          <span className="text-sm text-slate-700 max-w-[220px] truncate">
            {transcript || <span className="text-slate-400 italic">正在聆听...</span>}
          </span>
          {transcript && (
            <button
              onClick={() => { setTranscript(''); lastFinalRef.current = '' }}
              className="text-slate-400 hover:text-slate-600 flex-shrink-0"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      )}

      {/* Orb button */}
      <div className="pointer-events-auto relative flex items-center justify-center">
        {/* Pulse rings when listening */}
        {listening && (
          <>
            <span className="absolute w-16 h-16 rounded-full bg-violet-400/20 animate-ping" />
            <span className="absolute w-20 h-20 rounded-full bg-violet-400/10 animate-ping [animation-delay:0.3s]" />
          </>
        )}
        <button
          onClick={handleClick}
          disabled={disabled}
          title={listening ? '点击发送 / 再次点击停止' : '语音输入'}
          className={`relative flex h-14 w-14 cursor-pointer items-center justify-center rounded-full transition-all duration-200
            ${listening
              ? 'scale-110 bg-violet-600 shadow-[0_16px_34px_rgba(124,58,237,0.36)]'
              : 'border border-violet-200 bg-white shadow-[0_10px_28px_rgba(124,58,237,0.18)] hover:scale-105 hover:border-violet-400 hover:shadow-[0_14px_32px_rgba(124,58,237,0.24)]'
            }
            ${disabled ? 'opacity-40 cursor-not-allowed' : ''}
          `}
        >
          {listening
            ? <MicOff className="w-6 h-6 text-white" />
            : <Mic className="w-6 h-6 text-violet-500" />
          }
        </button>
      </div>
    </div>
  )
}
