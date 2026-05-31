import { createContext } from 'react'
import type { Language } from './dictionary'

type TranslationParams = Record<string, string | number>

export interface LanguageContextValue {
  language: Language
  setLanguage: (language: Language) => void
  toggleLanguage: () => void
  t: (key: string, params?: TranslationParams, fallback?: string) => string
}

export const LanguageContext = createContext<LanguageContextValue | null>(null)

