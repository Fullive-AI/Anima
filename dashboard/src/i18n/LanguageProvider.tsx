import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { DEFAULT_LANGUAGE, LANGUAGE_STORAGE_KEY, dictionary, type Language } from './dictionary'
import { LanguageContext } from './LanguageContext'

type TranslationParams = Record<string, string | number>

function getInitialLanguage(): Language {
  if (typeof window === 'undefined') return DEFAULT_LANGUAGE
  const saved = window.localStorage.getItem(LANGUAGE_STORAGE_KEY)
  return isLanguage(saved) ? saved : DEFAULT_LANGUAGE
}

function isLanguage(value: unknown): value is Language {
  return value === 'zh-CN' || value === 'en-US'
}

function readPath(source: unknown, key: string): string | undefined {
  const value = key.split('.').reduce<unknown>((current, part) => {
    if (current && typeof current === 'object' && part in current) {
      return (current as Record<string, unknown>)[part]
    }
    return undefined
  }, source)
  return typeof value === 'string' ? value : undefined
}

function interpolate(template: string, params?: TranslationParams) {
  if (!params) return template
  return template.replace(/\{\{(\w+)\}\}/g, (_, key: string) => String(params[key] ?? ''))
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(getInitialLanguage)

  const setLanguage = useCallback((nextLanguage: Language) => {
    setLanguageState(nextLanguage)
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, nextLanguage)
  }, [])

  const toggleLanguage = useCallback(() => {
    setLanguage(language === 'zh-CN' ? 'en-US' : 'zh-CN')
  }, [language, setLanguage])

  const t = useCallback((key: string, params?: TranslationParams, fallback?: string) => {
    const translated = readPath(dictionary[language], key) || readPath(dictionary[DEFAULT_LANGUAGE], key)
    return interpolate(translated || fallback || key, params)
  }, [language])

  const value = useMemo(() => ({
    language,
    setLanguage,
    toggleLanguage,
    t,
  }), [language, setLanguage, toggleLanguage, t])

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  )
}
