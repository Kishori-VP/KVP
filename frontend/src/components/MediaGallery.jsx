import { FileText, ImageOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import api from '../lib/api'
import { useFetch } from '../lib/hooks'
import { t } from '../lib/i18n'
import { Spinner } from './ui'

/** Load media files (they need the auth header, so plain <img src> cannot fetch them). */
export function useMediaUrls(media) {
  const [urls, setUrls] = useState({})
  useEffect(() => {
    let alive = true
    const created = []
    ;(async () => {
      for (const m of media || []) {
        try {
          const r = await api.get(`/media/${m.id}/file`, { responseType: 'blob' })
          const u = URL.createObjectURL(r.data)
          created.push(u)
          if (alive) setUrls((p) => ({ ...p, [m.id]: u }))
        } catch {
          if (alive) setUrls((p) => ({ ...p, [m.id]: null })) // missing file
        }
      }
    })()
    return () => { alive = false; created.forEach(URL.revokeObjectURL) }
  }, [media])
  return urls
}

/** Thumbnails of the given media records; click one to open it full size. `meta(m)` adds a line under each. */
export function MediaGrid({ media, empty, meta }) {
  const urls = useMediaUrls(media)
  if (!media?.length) return empty ? <p className="text-sm text-gray-500">{empty}</p> : null
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {media.map((m) => {
        const url = urls[m.id]
        return (
          <figure key={m.id} className="overflow-hidden rounded-lg border border-black/10">
            {url === undefined ? (
              <div className="flex h-32 items-center justify-center bg-gray-50"><Spinner /></div>
            ) : url === null ? (
              <div className="flex h-32 flex-col items-center justify-center gap-1 bg-gray-50 px-2 text-center text-xs text-gray-500">
                <ImageOff className="h-5 w-5" /> {t('File not available')}
              </div>
            ) : m.content_type?.startsWith('image/') ? (
              <a href={url} target="_blank" rel="noreferrer"><img src={url} alt={m.caption || m.original_name || ''} className="h-32 w-full object-cover" /></a>
            ) : (
              <a href={url} target="_blank" rel="noreferrer" className="flex h-32 items-center justify-center gap-1.5 bg-gray-50 px-2 text-xs text-brand-700 hover:underline">
                <FileText className="h-5 w-5 shrink-0" /> <span className="truncate">{m.original_name || m.content_type}</span>
              </a>
            )}
            {(m.caption || m.location) && (
              <figcaption className="truncate px-2 py-1 text-[11px] text-gray-500">
                {m.caption || `${m.location.lat.toFixed(4)}, ${m.location.lng.toFixed(4)}`}
              </figcaption>
            )}
            {meta && <div className="border-t border-black/5 px-2 py-1 text-[11px] leading-snug text-gray-600">{meta(m)}</div>}
          </figure>
        )
      })}
    </div>
  )
}

/** Photos attached to one record (home visit, case, …), fetched by the component itself. */
export default function MediaGallery({ entityType, entityId, refreshKey, empty = t('No photos attached.') }) {
  const { data, loading } = useFetch(entityId ? '/media' : null, { entity_type: entityType, entity_id: entityId, _r: refreshKey })
  if (loading && !data) return <Spinner />
  return <MediaGrid media={data} empty={empty} />
}
