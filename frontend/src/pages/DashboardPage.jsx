import { useState, useEffect } from 'react';
import { Card } from '../components/ui/Card';
import { Activity, Server, AlertTriangle, CheckCircle, Clock } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import api from '../api/config';
import { useNetworkContext } from '../contexts/NetworkContext';

export default function DashboardPage() {
    const { latencyHistory, addLatencyPoint, incidentLog } = useNetworkContext();
    const [stats, setStats] = useState({
        activeIncidentes: 0,
        avgLatency: 0,
        servicesCount: 3
    });
    const [services, setServices] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchStats = async () => {
        try {
            const res = await api.get('/tools/dashboard/status');
            const data = res.data;
            
            setStats({
                activeIncidentes: data.active_incidents,
                avgLatency: data.avg_latency,
                servicesCount: data.services.length
            });
            setServices(data.services);
            
            // Agregar punto al historial global (persistente)
            addLatencyPoint({
                time: new Date().toLocaleTimeString(),
                latency: Number(data.avg_latency)
            });
        } catch (err) {
            console.error("Dashboard fetch error", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        // Carga inicial
        fetchStats();
        
        // Polling cada 5 segundos
        const interval = setInterval(fetchStats, 5000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="container-app py-8 space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold text-dark-text-primary">Monitoreo de Red</h2>
                    <p className="text-dark-text-muted">Estado en tiempo real de servicios críticos.</p>
                </div>
                <div className="hidden sm:flex items-center gap-2 text-sm text-dark-text-muted bg-dark-bg-secondary px-3 py-1 rounded-full">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                    </span>
                    En vivo
                </div>
            </div>

            {/* KPIs Principales */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Card className="p-6 relative overflow-hidden">
                    <div className="relative z-10">
                        <div className="text-dark-text-muted text-sm font-medium mb-1">Latencia Promedio</div>
                        <div className="text-3xl font-bold text-dark-text-primary">
                            {stats ? `${stats.avgLatency} ms` : '...'}
                        </div>
                    </div>
                    <Activity className="absolute right-4 top-4 w-12 h-12 text-blue-500/10" />
                    <div className="absolute inset-x-0 bottom-0 h-1 bg-gradient-to-r from-blue-500 to-cyan-400"></div>
                </Card>
                
                <Card className="p-6 relative overflow-hidden flex flex-col justify-between">
                    <div className="relative z-10">
                        <div className="text-dark-text-muted text-sm font-medium mb-1">Servicios Monitoreados</div>
                        <div className="text-3xl font-bold text-dark-text-primary mb-1">
                             <p className="text-xl font-medium">
                                Verificando Internet, Router y Sistema
                             </p>
                        </div>
                        
                    </div>
                    <Server className="absolute right-4 top-4 w-12 h-12 text-purple-500/10" />
                    <div className="absolute inset-x-0 bottom-0 h-1 bg-gradient-to-r from-purple-500 to-pink-500"></div>
                </Card>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Gráfico de Latencia */}
                <Card className="lg:col-span-2 p-6 flex flex-col h-[400px]">
                    <h3 className="text-lg font-bold text-dark-text-primary mb-6 flex items-center gap-2">
                        Historial de Latencia
                        <Clock className="w-4 h-4 text-blue-400" />
                    </h3>
                    {/* Contenedor con scroll horizontal para móviles */}
                    <div className="w-full flex-1 overflow-x-auto overflow-y-hidden">
                        <div style={{ width: '800px', height: '300px' }}>
                             {/* Usamos dimensiones fijas (800x300) que funcionan perfecto */}
                             <AreaChart width={800} height={300} data={latencyHistory} key={latencyHistory.length}>
                                    <defs>
                                        <linearGradient id="colorLatency" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                                            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                                    <XAxis dataKey="time" hide />
                                    <YAxis 
                                        stroke="#94a3b8" 
                                        fontSize={12} 
                                        tickLine={false} 
                                        axisLine={false} 
                                        domain={[0, 'auto']} 
                                        allowDataOverflow={false}
                                    />
                                    <Tooltip 
                                        contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                                        itemStyle={{ color: '#e2e8f0' }}
                                    />
                                    <Area 
                                        type="monotone" 
                                        dataKey="latency" 
                                        stroke="#3b82f6" 
                                        strokeWidth={3} 
                                        fillOpacity={1} 
                                        fill="url(#colorLatency)" 
                                        isAnimationActive={false}
                                    />
                                </AreaChart>
                        </div>
                    </div>
                </Card>

                {/* Bitácora de Incidentes (Análisis de Sesión Persistente) */}
                <Card className="p-6 h-[400px] flex flex-col">
                    <h3 className="text-lg font-bold text-dark-text-primary mb-4 flex items-center gap-2">
                         <AlertTriangle className="w-4 h-4 text-orange-400" />
                        Bitácora de Incidentes
                    </h3>
                    
                    <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
                        {incidentLog.length === 0 ? (
                             <div className="h-full flex flex-col items-center justify-center text-center text-dark-text-muted opacity-60">
                                <CheckCircle className="w-12 h-12 mb-3 text-green-500" />
                                <p className="font-medium">Todo en orden</p>
                                <p className="text-sm">No hemos detectado fallas desde que abriste la app.</p>
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {incidentLog.map((ev) => {
                                    if (ev.type === 'recovery') {
                                        return (
                                                <div key={ev.id} className="p-3 rounded-lg border flex items-start gap-3 bg-green-500/10 border-green-500/20">
                                                <CheckCircle className="w-5 h-5 text-green-400 shrink-0 mt-0.5" />
                                                <div>
                                                    <div className="text-sm font-medium text-green-400">
                                                        ¡Ya volvió la señal!
                                                    </div>
                                                    <div className="text-xs text-dark-text-muted mt-1">
                                                        Hora: <span className="text-dark-text-primary">{ev.time}</span> • 
                                                        Estable: <span className="font-mono">{ev.value.toFixed(0)}ms</span>
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    }
                                    
                                    // Issue event
                                    return (
                                        <div key={ev.id} className={`p-3 rounded-lg border flex items-start gap-3 ${
                                            ev.isOutage 
                                                ? 'bg-red-500/10 border-red-500/20' 
                                                : 'bg-yellow-500/10 border-yellow-500/20'
                                        }`}>
                                            {ev.isOutage ? (
                                                <AlertTriangle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                                            ) : (
                                                <Activity className="w-5 h-5 text-yellow-400 shrink-0 mt-0.5" />
                                            )}
                                            <div>
                                                <div className={`text-sm font-medium ${
                                                    ev.isOutage ? 'text-red-400' : 'text-yellow-400'
                                                }`}>
                                                    {ev.isOutage ? 'Se nos fue el internet (Posible corte)' : 'El internet está lento'}
                                                </div>
                                                <div className="text-xs text-dark-text-muted mt-1">
                                                    Hora: <span className="text-dark-text-primary">{ev.time}</span> • 
                                                    Pico: <span className="font-mono">{ev.value.toFixed(0)}ms</span>
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                </Card>
            </div>
        </div>
    );
}
