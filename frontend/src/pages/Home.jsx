import { ChevronLeft, ChevronRight, LogIn, Mail, MapPin, Phone } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import logo from '../assets/SEDT_logo.png'
import { useAuth } from '../lib/auth'
import { LANGUAGES, t, useLang } from '../lib/i18n'

// Public landing page introducing SEDT. Figures are taken from sedtindia.org.
const STATS = [
  { value: '1980', label: 'Working since' },
  { value: '25,000+', label: 'Adolescent girls reached' },
  { value: '55+', label: 'Villages under Kishori Vikas' },
  { value: '50,000+', label: 'Children supported by Childline' },
]

// Eagerly import all slideshow images from assets/slideshow
const slideshowModules = import.meta.glob(
  '../assets/slideshow/*.{jpg,jpeg,png,webp,avif,JPG,JPEG,PNG,WEBP,AVIF}',
  { eager: true, import: 'default' }
)
const SLIDESHOW_IMAGES = Object.keys(slideshowModules)
  .sort()
  .map((k) => slideshowModules[k])

function Slideshow() {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isPaused, setIsPaused] = useState(false)
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false)
  const touchStartXRef = useRef(null)
  const touchEndXRef = useRef(null)

  const count = SLIDESHOW_IMAGES.length

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setPrefersReducedMotion(mq.matches)
    const listener = (e) => setPrefersReducedMotion(e.matches)
    mq.addEventListener?.('change', listener)
    return () => mq.removeEventListener?.('change', listener)
  }, [])

  const nextSlide = () => {
    setCurrentIndex((prev) => (prev + 1) % count)
  }

  const prevSlide = () => {
    setCurrentIndex((prev) => (prev - 1 + count) % count)
  }

  const goToSlide = (idx) => {
    setCurrentIndex(idx)
  }

  useEffect(() => {
    if (count <= 1 || isPaused || prefersReducedMotion) return

    const timer = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % count)
    }, 4500)

    return () => clearInterval(timer)
  }, [isPaused, prefersReducedMotion, count])

  if (count === 0) return null

  const handleTouchStart = (e) => {
    touchStartXRef.current = e.targetTouches[0].clientX
    touchEndXRef.current = null
  }

  const handleTouchMove = (e) => {
    touchEndXRef.current = e.targetTouches[0].clientX
  }

  const handleTouchEnd = () => {
    if (touchStartXRef.current === null || touchEndXRef.current === null) return
    const diff = touchStartXRef.current - touchEndXRef.current
    const threshold = 40
    if (diff > threshold) {
      nextSlide()
    } else if (diff < -threshold) {
      prevSlide()
    }
    touchStartXRef.current = null
    touchEndXRef.current = null
  }

  return (
    <section className="mt-14" aria-label="Photo Slideshow">
      <div
        tabIndex={0}
        role="region"
        aria-roledescription="carousel"
        aria-label="Image Slideshow"
        className="group relative w-full overflow-hidden rounded-2xl border border-white/80 bg-white/90 shadow-sm focus:outline-none focus:ring-2 focus:ring-brand-500/50"
        onMouseEnter={() => setIsPaused(true)}
        onMouseLeave={() => setIsPaused(false)}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onKeyDown={(e) => {
          if (e.key === 'ArrowLeft') prevSlide()
          if (e.key === 'ArrowRight') nextSlide()
        }}
      >
        <div className="relative h-64 w-full overflow-hidden sm:h-80 md:h-[420px] lg:h-[480px]">
          <div
            className={`flex h-full w-full ${prefersReducedMotion ? '' : 'transition-transform duration-500 ease-out'}`}
            style={{ transform: `translateX(-${currentIndex * 100}%)` }}
          >
            {SLIDESHOW_IMAGES.map((src, idx) => (
              <div key={idx} className="relative h-full w-full shrink-0">
                <img
                  src={src}
                  alt=""
                  loading={idx === 0 ? 'eager' : 'lazy'}
                  className="h-full w-full select-none object-cover"
                  draggable={false}
                />
              </div>
            ))}
          </div>

          {/* Navigation Arrows */}
          <button
            type="button"
            onClick={prevSlide}
            aria-label="Previous slide"
            className="absolute left-3 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-white/85 text-gray-800 shadow-md backdrop-blur-md transition-all hover:bg-white hover:scale-105 active:scale-95 focus:outline-none focus:ring-2 focus:ring-brand-500 sm:left-4 sm:h-12 sm:w-12"
          >
            <ChevronLeft className="h-5 w-5 sm:h-6 sm:w-6" />
          </button>
          <button
            type="button"
            onClick={nextSlide}
            aria-label="Next slide"
            className="absolute right-3 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-white/85 text-gray-800 shadow-md backdrop-blur-md transition-all hover:bg-white hover:scale-105 active:scale-95 focus:outline-none focus:ring-2 focus:ring-brand-500 sm:right-4 sm:h-12 sm:w-12"
          >
            <ChevronRight className="h-5 w-5 sm:h-6 sm:w-6" />
          </button>

          {/* Pagination Dots */}
          <div className="absolute bottom-3 left-1/2 flex max-w-[90%] -translate-x-1/2 flex-wrap items-center justify-center gap-1.5 rounded-full bg-black/45 px-3 py-1.5 backdrop-blur-md sm:bottom-4">
            {SLIDESHOW_IMAGES.map((_, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => goToSlide(idx)}
                aria-label={`Go to slide ${idx + 1}`}
                className={`rounded-full transition-all duration-300 focus:outline-none ${
                  currentIndex === idx
                    ? 'h-2 w-5 bg-white shadow-sm'
                    : 'h-2 w-2 bg-white/50 hover:bg-white/85'
                }`}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

export default function Home() {
  const { user } = useAuth()
  const { lang, setLang } = useLang()

  return (
    <div className="min-h-full bg-gradient-to-br from-brand-50 via-white to-brand-100/60">
      <header className="mx-auto flex min-h-20 max-w-6xl items-center justify-end gap-3 px-4 py-4 sm:px-8">
        <div className="flex items-center gap-2">
          <div className="flex gap-1 text-xs">
            {LANGUAGES.map((l) => (
              <button
                key={l.value}
                type="button"
                onClick={() => setLang(l.value)}
                className={lang === l.value ? 'rounded px-2 py-0.5 font-semibold text-brand-700' : 'rounded px-2 py-0.5 text-gray-500 hover:bg-gray-100'}
              >
                {l.label}
              </button>
            ))}
          </div>
          <Link
            to={user ? '/' : '/login'}
            className="bg-brand-gradient bg-brand-gradient-hover inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium text-white shadow-md shadow-brand-800/15"
          >
            <LogIn className="h-4 w-4" />
            {user ? t('Go to dashboard') : t('Log in')}
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 pb-16 sm:px-8">
        <section className="grid items-center gap-10 py-10 md:grid-cols-[1.3fr_1fr] md:py-16">
          <div>
            <p className="mb-3 text-sm font-semibold uppercase tracking-wide text-brand-600">{t('KISHORI VIKAS PROGRAMME')}</p>
            <h1 className="text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              {t('An initiative by Socio-Economic Development Trust & YX Gives USA')}
            </h1>
          </div>
          <div className="flex justify-center">
            <img src={logo} alt="" className="w-56 drop-shadow-xl sm:w-72" />
          </div>
        </section>

        <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {STATS.map((s) => (
            <div key={s.label} className="rounded-2xl border border-white/80 bg-white/90 p-5 text-center shadow-sm">
              <div className="text-brand-gradient text-2xl font-bold sm:text-3xl">{s.value}</div>
              <div className="mt-1 text-xs text-gray-500 sm:text-sm">{t(s.label)}</div>
            </div>
          ))}
        </section>

        <Slideshow />

        <section className="mt-14 rounded-2xl border border-white/80 bg-white/90 p-6 shadow-sm">
          <h2 className="mb-4 text-xl font-semibold text-gray-900">{t('Contact')}</h2>
          <div className="grid gap-4 text-sm text-gray-600 sm:grid-cols-3">
            <div className="flex gap-2">
              <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
              <span>Post Kerwadi, Taluka Palam, District Parbhani, Maharashtra 431 720</span>
            </div>
            <a href="tel:+919922914102" className="flex gap-2 hover:text-brand-700">
              <Phone className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
              +91 99229 14102
            </a>
            <a href="mailto:sedtindia@gmail.com" className="flex gap-2 hover:text-brand-700">
              <Mail className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
              sedtindia@gmail.com
            </a>
          </div>
          <a href="https://sedtindia.org/" target="_blank" rel="noreferrer" className="mt-4 inline-block text-sm font-medium text-brand-700 hover:underline">
            {t('Visit sedtindia.org')} →
          </a>
        </section>
      </main>
    </div>
  )
}
