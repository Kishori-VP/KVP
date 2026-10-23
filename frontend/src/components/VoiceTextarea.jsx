import { Mic, Square } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button, Field, Textarea } from './ui'
import { t } from '../lib/i18n'

export default function VoiceTextarea({
  label,
  value,
  onChange,
  placeholder,
  rows = 3,
  defaultLang = 'mr-IN',
  hint,
}) {
  const [listening, setListening] = useState(false)
  const [interimText, setInterimText] = useState('')
  const [voiceError, setVoiceError] = useState('')
  const [speechLang, setSpeechLang] = useState(defaultLang) // 'mr-IN' (Marathi) or 'en-IN' (English)

  const isListeningRef = useRef(false)
  const recognitionRef = useRef(null)
  const baseTextRef = useRef('')
  const accumulatedRef = useRef('')

  const startVoice = () => {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!Recognition) {
      setVoiceError(
        t('Voice input is not supported in this browser. Please use Chrome on Android or desktop.')
      )
      return
    }

    setVoiceError('')
    setInterimText('')
    baseTextRef.current = value || ''
    accumulatedRef.current = ''
    isListeningRef.current = true

    try {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort()
        } catch {}
      }

      const recognition = new Recognition()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = speechLang
      recognitionRef.current = recognition

      recognition.onresult = (event) => {
        let interim = ''
        let finalChunk = ''

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const res = event.results[i]
          const transcript = res[0]?.transcript || ''
          if (res.isFinal) {
            finalChunk += (finalChunk ? ' ' : '') + transcript
          } else {
            interim += (interim ? ' ' : '') + transcript
          }
        }

        if (finalChunk) {
          const currentAccum = accumulatedRef.current
            ? `${accumulatedRef.current} ${finalChunk.trim()}`
            : finalChunk.trim()
          accumulatedRef.current = currentAccum

          const newFullText = baseTextRef.current
            ? `${baseTextRef.current.trim()} ${currentAccum}`
            : currentAccum
          onChange(newFullText)
        }

        setInterimText(interim)
      }

      recognition.onerror = (event) => {
        if (event.error === 'no-speech' || event.error === 'aborted') {
          return
        }
        if (event.error === 'not-allowed') {
          isListeningRef.current = false
          setListening(false)
          setVoiceError(t('Microphone permission denied. Please allow microphone access.'))
          return
        }
        console.warn('Speech recognition notice:', event.error)
      }

      recognition.onend = () => {
        if (isListeningRef.current) {
          try {
            recognition.start()
          } catch (e) {
            // Already started or busy
          }
        } else {
          setListening(false)
          setInterimText('')
        }
      }

      recognition.start()
      setListening(true)
    } catch (err) {
      console.error('Error starting speech recognition:', err)
      setVoiceError(t('Could not start microphone. Please check permissions.'))
      isListeningRef.current = false
      setListening(false)
    }
  }

  const stopVoice = () => {
    isListeningRef.current = false
    setListening(false)
    setInterimText('')
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop()
      } catch {}
    }
  }

  useEffect(() => {
    return () => {
      isListeningRef.current = false
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort()
        } catch {}
      }
    }
  }, [])

  return (
    <Field label={label} hint={hint}>
      <div className="relative">
        <Textarea
          rows={rows}
          placeholder={placeholder}
          value={value || ''}
          onChange={(e) => {
            onChange(e.target.value)
            if (isListeningRef.current) {
              baseTextRef.current = e.target.value
              accumulatedRef.current = ''
            }
          }}
          className={listening ? 'border-red-400 ring-1 ring-red-400' : ''}
        />
        {listening && interimText && (
          <div className="mt-1 flex items-center gap-1.5 rounded border border-red-200 bg-red-50/70 p-1.5 text-xs text-red-900">
            <span className="inline-block h-2 w-2 shrink-0 animate-ping rounded-full bg-red-500" />
            <span className="truncate italic">"{interimText}"</span>
          </div>
        )}
      </div>

      <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {listening ? (
            <Button
              size="sm"
              variant="danger"
              onClick={stopVoice}
              className="flex items-center gap-1.5 bg-red-600 font-bold text-white shadow hover:bg-red-700 active:scale-95 animate-pulse"
            >
              <Square className="h-3.5 w-3.5 fill-current" />
              <span>{t('Stop Voice Typing')}</span>
            </Button>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              icon={Mic}
              onClick={startVoice}
              className="border-brand-300 text-brand-800 hover:bg-brand-50"
            >
              <span>
                {speechLang === 'mr-IN'
                  ? t('Start Voice Typing (Marathi)')
                  : t('Start Voice Typing (English)')}
              </span>
            </Button>
          )}

          <button
            type="button"
            onClick={() => {
              const next = speechLang === 'mr-IN' ? 'en-IN' : 'mr-IN'
              setSpeechLang(next)
              if (isListeningRef.current) {
                stopVoice()
              }
            }}
            className="rounded px-2 py-1 text-xs font-semibold text-gray-600 hover:bg-gray-100 hover:text-brand-700"
            title={t('Switch voice typing language')}
          >
            {speechLang === 'mr-IN' ? 'English (EN)' : 'मराठी (MR)'}
          </button>
        </div>

        {listening && (
          <span className="flex items-center gap-1.5 text-xs font-medium text-red-600">
            <span className="h-2 w-2 rounded-full bg-red-600 animate-pulse" />
            {t('Recording… Pauses will not stop typing. Hit Stop when done.')}
          </span>
        )}

        {voiceError && <span className="text-xs text-amber-700">{voiceError}</span>}
      </div>
    </Field>
  )
}
