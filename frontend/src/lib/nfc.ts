// Web NFC (Chrome on Android, HTTPS only). A SMARTLAB tag holds two NDEF records:
// a URL "<origin>/?scan=<ID>" (tapping it with the app closed opens the right card) and a text record "<ID>".

interface NdefRecord { recordType: string; data?: DataView; encoding?: string; mediaType?: string }
interface NdefReadingEvent extends Event { serialNumber: string; message: { records: NdefRecord[] } }
interface NdefReader extends EventTarget {
  scan: (opts?: { signal?: AbortSignal }) => Promise<void>
  write: (msg: { records: { recordType: string; data: string; lang?: string }[] }, opts?: { signal?: AbortSignal; overwrite?: boolean }) => Promise<void>
  onreading: ((e: NdefReadingEvent) => void) | null
  onreadingerror: ((e: Event) => void) | null
}
declare global {
  interface Window { NDEFReader?: new () => NdefReader }
}

export type NfcTag = { serial: string; records: string[] }

export const nfcSupported = () => typeof window !== 'undefined' && 'NDEFReader' in window
export const nfcNeedsHttps = () => typeof window !== 'undefined' && !window.isSecureContext

function decode(r: NdefRecord): string | null {
  if (!r.data || !['text', 'url', 'absolute-url'].includes(r.recordType)) return null
  try {
    return new TextDecoder(r.encoding || 'utf-8').decode(r.data).trim()
  } catch {
    return null
  }
}

/** Listen for tags until the signal aborts. Calls onTag for every tag read. */
export async function readNfc(signal: AbortSignal, onTag: (tag: NfcTag) => void, onError: (msg: string) => void) {
  const reader = new window.NDEFReader!()
  reader.onreading = (e) => onTag({ serial: e.serialNumber, records: e.message.records.map(decode).filter((x): x is string => !!x) })
  reader.onreadingerror = () => onError('read')
  await reader.scan({ signal })
}

/** Write a SMARTLAB tag for an asset, material or sample ID. Resolves once the tag was written. */
export async function writeNfc(code: string, signal?: AbortSignal) {
  const reader = new window.NDEFReader!()
  await reader.write({
    records: [
      { recordType: 'url', data: `${location.origin}/?scan=${encodeURIComponent(code)}` },
      { recordType: 'text', data: code, lang: 'en' },
    ],
  }, { signal, overwrite: true })
}
