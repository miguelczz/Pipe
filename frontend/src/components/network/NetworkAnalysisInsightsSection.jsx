import { Card } from '../ui/Card'
import { WiresharkTruthPanel } from '../WiresharkTruthPanel'
import { MarkdownRenderer } from '../chat/MarkdownRenderer'

/**
 * Paneles inferiores: Wireshark "source of truth" + análisis en markdown.
 * Componente de presentación puro.
 */
export function NetworkAnalysisInsightsSection({
  result,
  fileMetadata,
  savedSsid,
  userSsid,
}) {
  if (!result) return null

  const showWireshark = !!result.stats?.diagnostics?.wireshark_raw
  const showAnalysis = !!result.analysis

  if (!showWireshark && !showAnalysis) {
    return null
  }

  return (
    <>
      {showWireshark && (
        <Card className="p-6">
          <WiresharkTruthPanel
            wiresharkRaw={result.stats.diagnostics.wireshark_raw}
            wiresharkCompare={result.stats.diagnostics.wireshark_compare}
            ssid={savedSsid || fileMetadata?.ssid || userSsid}
          />
        </Card>
      )}

      {showAnalysis && (
        <Card className="p-6">
          <div className="max-w-none">
            <div className="text-dark-text-primary leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
              <MarkdownRenderer content={result.analysis || ''} />
            </div>
          </div>
        </Card>
      )}
    </>
  )
}

