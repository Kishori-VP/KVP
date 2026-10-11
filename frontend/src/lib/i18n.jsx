import { Fragment, createContext, useContext, useEffect, useState } from 'react'
import mr from './mr'

/**
 * Lightweight translation: UI strings are written in English and looked up in the
 * Marathi dictionary, falling back to English when a string has no entry.
 * `t` is a plain function (not a hook) so it also works in module-level label lists
 * and helpers; the provider remounts its subtree when the language changes.
 */

const LANG_KEY = 'kvp_lang'
const DICTS = { mr }
export const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'mr', label: 'मराठी' },
]

function storedLang() {
  try {
    return localStorage.getItem(LANG_KEY) || 'en'
  } catch {
    return 'en'
  }
}

let current = storedLang()

export function getLang() {
  return current
}

/** Translate `text`; `{name}` placeholders are filled from `vars`. */
export function t(text, vars) {
  let out = DICTS[current]?.[text] ?? text
  if (vars) out = out.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m))
  return out
}

/** Show an English/Marathi name pair with the current language first. */
export function bilingual(en, mr, sep = ' · ') {
  if (!mr) return en
  return current === 'mr' ? `${mr}${sep}${en}` : `${en}${sep}${mr}`
}

/** Locale for Intl formatting (Latin digits are kept for readability of figures). */
export function locale() {
  return current === 'mr' ? 'mr-IN-u-nu-latn' : 'en-IN'
}

const LangContext = createContext({ lang: current, setLang: () => {} })

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(current)

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const setLang = (next) => {
    current = next
    try {
      localStorage.setItem(LANG_KEY, next)
    } catch {
      /* storage unavailable - choice lasts for this page load */
    }
    setLangState(next)
  }

  return (
    <LangContext.Provider value={{ lang, setLang }}>
      <Fragment key={lang}>{children}</Fragment>
    </LangContext.Provider>
  )
}

export function useLang() {
  return useContext(LangContext)
}
