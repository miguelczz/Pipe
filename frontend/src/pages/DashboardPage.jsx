import { useState, useEffect } from 'react';
import { Card } from '../components/ui/Card';
import { Activity, Server, AlertTriangle, CheckCircle, Clock } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
});

// Mock data para gráfico inicial (mientras carga real)
const initialData = Array.from({ length: 20 }, (_, i) => ({
  time: new Date(Date.now() - (20 - i) * 1000).toLocaleTimeString(),
  latency: 10 + Math.random() * 20
}));

export default function DashboardPage() {
    const [stats, setStats] = useState(null);
    const [history, setHistory] = useState(initialData);
    const [loading, setLoading] = useState(true);

    const fetchStats = async () => {
        try {
            const res = await api.get('/tools/dashboard/status');
            const data = res.data;
            setStats(data);
            
            // Actualizar historial con nueva latencia promedio
            setHistory(prev => {
                const newPoint = {
                    time: new Date().toLocaleTimeString(),
                    latency: data.avg_latency
                };
                return [...prev.slice(1), newPoint];
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
                    <h2 className="text-2xl font-bold text-dark-text-primary">Dashboard de Red</h2>
                    <p className="text-dark-text-muted">Monitoreo en tiempo real de servicios críticos.</p>
                </div>
                <div className="flex items-center gap-2 text-sm text-dark-text-muted bg-dark-bg-secondary px-3 py-1 rounded-full">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                    </span>
                    Actualización en vivo
                </div>
            </div>

            {/* KPIs Principales */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <Card className="p-6 relative overflow-hidden">
                    <div className="relative z-10">
                        <div className="text-dark-text-muted text-sm font-medium mb-1">Latencia Promedio</div>
                        <div className="text-3xl font-bold text-dark-text-primary">
                            {stats ? `${stats.avg_latency} ms` : '...'}
                        </div>
                    </div>
                    <Activity className="absolute right-4 top-4 w-12 h-12 text-blue-500/10" />
                    <div className="absolute inset-x-0 bottom-0 h-1 bg-gradient-to-r from-blue-500 to-cyan-400"></div>
                </Card>
                
                <Card className="p-6 relative overflow-hidden">
                    <div className="relative z-10">
                        <div className="text-dark-text-muted text-sm font-medium mb-1">Incidentes Activos</div>
                        <div className="text-3xl font-bold text-dark-text-primary">
                             {stats ? stats.active_incidents : 0}
                        </div>
                    </div>
                    {stats?.active_incidents > 0 ? (
                        <AlertTriangle className="absolute right-4 top-4 w-12 h-12 text-red-500/10" />
                    ) : (
                        <CheckCircle className="absolute right-4 top-4 w-12 h-12 text-green-500/10" />
                    )}
                     <div className={`absolute inset-x-0 bottom-0 h-1 ${stats?.active_incidents > 0 ? 'bg-red-500' : 'bg-green-500'}`}></div>
                </Card>
                
                <Card className="p-6 relative overflow-hidden">
                    <div className="relative z-10">
                        <div className="text-dark-text-muted text-sm font-medium mb-1">Servicios Monitoreados</div>
                        <div className="text-3xl font-bold text-dark-text-primary">
                             {stats ? stats.services.length : 3}
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
                        <Clock className="w-4 h-4 text-blue-400" />
                        Historial de Latencia (Global)
                    </h3>
                    <div className="flex-1 w-full min-h-0">
                         <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={history}>
                                <defs>
                                    <linearGradient id="colorLatency" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                                <XAxis dataKey="time" hide />
                                <YAxis stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} />
                                <Tooltip 
                                    contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                                    itemStyle={{ color: '#e2e8f0' }}
                                />
                                <Area type="monotone" dataKey="latency" stroke="#3b82f6" strokeWidth={2} fillOpacity={1} fill="url(#colorLatency)" />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </Card>

                {/* Lista de Servicios */}
                <Card className="p-6 h-[400px] overflow-auto">
                    <h3 className="text-lg font-bold text-dark-text-primary mb-4 flex items-center gap-2">
                         <Server className="w-4 h-4 text-purple-400" />
                        Estado de Servicios
                    </h3>
                    <div className="space-y-4">
                        {loading && !stats ? (
                            <div className="text-center text-dark-text-muted py-10">Cargando métricas...</div>
                        ) : (
                            stats?.services.map((svc, idx) => (
                                <div key={idx} className="flex items-center justify-between p-3 rounded-lg bg-dark-bg-secondary border border-dark-border-primary/50">
                                    <div className="flex items-center gap-3">
                                        <div className={`w-2.5 h-2.5 rounded-full ${
                                            svc.status === 'operational' ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]' : 
                                            svc.status === 'degraded' ? 'bg-yellow-500' : 'bg-red-500'
                                        }`}></div>
                                        <div>
                                            <div className="font-medium text-dark-text-primary text-sm">{svc.name}</div>
                                            <div className="text-xs text-dark-text-muted">Uptime: {svc.uptime_percentage}%</div>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-sm font-mono text-dark-text-primary">{svc.latency_ms.toFixed(1)} ms</div>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </Card>
            </div>
        </div>
    );
}
