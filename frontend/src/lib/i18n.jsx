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

/** The name in the current language only: Marathi after switching to मराठी, otherwise English. */
export function bilingual(en, mr) {
  return current === 'mr' ? mr || en : en || mr
}

/**
 * Name of a record (girl, group, village…) in the current language.
 * Girls and groups are entered in Marathi (`name`) and get an English spelling (`name_en`);
 * villages and talukas have an English `name` and a Marathi `name_mr`.
 */
export function localName(obj) {
  if (!obj) return ''
  return current === 'mr' ? obj.name_mr || obj.name || obj.name_en || '' : obj.name_en || obj.name || obj.name_mr || ''
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
