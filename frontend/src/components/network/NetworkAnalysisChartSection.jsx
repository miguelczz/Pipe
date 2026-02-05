import { Card } from '../ui/Card'
import { Activity } from 'lucide-react'
import { BandSteeringChart } from '../charts/BandSteeringChart'

/**
 * Sección de gráfica de Band Steering.
 * Componente de presentación puro.
 */
export function NetworkAnalysisChartSection({ result }) {
  if (!result?.band_steering) {
    return null
  }

  return (
    <Card className="lg:col-span-2 p-6 flex flex-col h-full">
      <div className="flex items-center gap-2 mb-4">
        <Activity className="w-5 h-5 text-dark-accent-primary" />
        <h3 className="text-lg font-semibold text-dark-text-primary">
          Visualización de Cambios de Banda
        </h3>
      </div>
      <div className="flex-1 min-h-[300px]">
        <BandSteeringChart
          btmEvents={result.band_steering?.btm_events || []}
          transitions={result.band_steering?.transitions || []}
          signalSamples={result.band_steering?.signal_samples || []}
          rawStats={result.stats || {}}
        />
      </div>
    </Card>
  )
}

