import { useState } from 'react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { MapPin, Globe, Loader2, Navigation } from 'lucide-react';
import axios from 'axios';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

// Fix para iconos de Leaflet en React (problema común de webpack/vite)
import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

let DefaultIcon = L.icon({
    iconUrl: icon,
    shadowUrl: iconShadow,
    iconSize: [25, 41],
    iconAnchor: [12, 41]
});
L.Marker.prototype.options.icon = DefaultIcon;

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
});

// Componente para re-centrar el mapa
function ChangeView({ center }) {
    const map = useMap();
    map.setView(center, map.getZoom());
    return null;
}

export default function GeoTracePage() {
    const [host, setHost] = useState('');
    const [points, setPoints] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [center, setCenter] = useState([20, 0]); // Centro inicial global

    const handleTrace = async () => {
        if(!host) return;
        setLoading(true);
        setError('');
        setPoints([]);
        
        try {
            const res = await api.get(`/tools/geo-trace?host=${encodeURIComponent(host)}`);
            const data = res.data;
            
            if (data.length === 0) {
                setError('No se encontraron datos geográficos para esta ruta (¿IPs privadas?)');
            } else {
                setPoints(data);
                // Centrar en el primer punto (origen aproximado) o destino
                if (data.length > 0) {
                    setCenter([data[0].lat, data[0].lon]);
                }
            }
        } catch (err) {
            setError(err.response?.data?.detail || 'Error al ejecutar trazado');
        } finally {
            setLoading(false);
        }
    };

    const polylinePositions = points.map(p => [p.lat, p.lon]);

    return (
        <div className="container-app py-8 h-[calc(100vh-64px)] flex flex-col">
            <div className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h2 className="text-2xl font-bold text-dark-text-primary flex items-center gap-2">
                        <Globe className="w-6 h-6 text-blue-500" />
                        Geo-Trace Visualizer
                    </h2>
                    <p className="text-dark-text-muted">Visualiza la ruta física que toman tus paquetes.</p>
                </div>
                
                <div className="flex gap-2 w-full md:w-auto">
                    <input 
                        type="text" 
                        placeholder="Dominio o IP (ej: google.com)" 
                        value={host}
                        onChange={(e) => setHost(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleTrace()}
                        className="flex-1 md:w-64 bg-dark-bg-secondary border border-dark-border-primary rounded-lg px-4 py-2 text-dark-text-primary focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <Button onClick={handleTrace} disabled={loading} className="min-w-[100px]">
                        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Trazar Ruta'}
                    </Button>
                </div>
            </div>

            {error && (
                <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-lg mb-4">
                    {error}
                </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 min-h-0">
                {/* Mapa */}
                <div className="lg:col-span-2 bg-dark-bg-secondary rounded-xl overflow-hidden border border-dark-border-primary relative z-0">
                    <MapContainer center={[20, 0]} zoom={2} style={{ height: '100%', width: '100%' }}>
                         {points.length > 0 && <ChangeView center={center} />}
                        <TileLayer
                            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                        />
                        {/* Línea de ruta */}
                        {points.length > 1 && <Polyline positions={polylinePositions} color="#3b82f6" weight={3} opacity={0.7} />}
                        
                        {/* Marcadores */}
                        {points.map((p, idx) => (
                            <Marker key={idx} position={[p.lat, p.lon]}>
                                <Popup>
                                    <div className="text-black text-sm">
                                        <strong>Salto #{p.hop}</strong><br/>
                                        IP: {p.ip}<br/>
                                        {p.city}, {p.country}
                                    </div>
                                </Popup>
                            </Marker>
                        ))}
                    </MapContainer>
                </div>

                {/* Lista de Saltos */}
                <Card className="flex flex-col overflow-hidden h-full">
                    <div className="p-4 border-b border-dark-border-primary bg-dark-bg-secondary">
                        <h3 className="font-bold text-dark-text-primary flex items-center gap-2">
                            <Navigation className="w-4 h-4 text-purple-400" />
                            Detalle de Saltos
                        </h3>
                    </div>
                    <div className="overflow-auto flex-1 p-0">
                        {points.length === 0 ? (
                            <div className="flex flex-col items-center justify-center h-full text-dark-text-muted p-8 text-center">
                                <MapPin className="w-12 h-12 mb-4 opacity-20" />
                                <p>Ingresa un destino para ver la ruta geográfica.</p>
                            </div>
                        ) : (
                            <table className="w-full text-sm text-left">
                                <thead className="text-xs text-dark-text-muted uppercase bg-dark-bg-tertiary sticky top-0">
                                    <tr>
                                        <th className="px-4 py-3">#</th>
                                        <th className="px-4 py-3">Ubicación</th>
                                        <th className="px-4 py-3">IP</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {points.map((p, idx) => (
                                        <tr key={idx} 
                                            className="border-b border-dark-border-primary/30 last:border-0 hover:bg-dark-bg-tertiary cursor-pointer transition-colors"
                                            onClick={() => setCenter([p.lat, p.lon])}
                                        >
                                            <td className="px-4 py-3 text-dark-text-muted font-mono">{p.hop}</td>
                                            <td className="px-4 py-3">
                                                <div className="font-medium text-dark-text-primary">{p.country}</div>
                                                <div className="text-xs text-dark-text-muted">{p.city}</div>
                                            </td>
                                            <td className="px-4 py-3 font-mono text-xs text-blue-400">{p.ip}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                </Card>
            </div>
        </div>
    );
}
