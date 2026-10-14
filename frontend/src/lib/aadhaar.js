import api from './api'

export const AADHAAR_SIDES = [
  { kind: 'aadhaar_front', label: 'Aadhaar card – front' },
  { kind: 'aadhaar_back', label: 'Aadhaar card – back' },
]

/** Upload one side of a girl's Aadhaar card; the server replaces any earlier file of that side. */
export function uploadAadhaar(girlId, kind, file) {
  const fd = new FormData()
  fd.append('entity_type', 'girl')
  fd.append('entity_id', girlId)
  fd.append('kind', kind)
  fd.append('file', file)
  return api.post('/media', fd)
}
