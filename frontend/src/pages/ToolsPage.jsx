import { useState } from 'react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Network, Search, Calculator, Check, AlertCircle } from 'lucide-react';
import axios from 'axios';

// Utilidad para llamadas API (reemplazar con instancia axios configurada si existe)
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
});

// SUBCOMPONENTES
const SubnetCalculator = () => {
    const [cidr, setCidr] = useState('');
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const calculate = async () => {
        setLoading(true);
        setError('');
        setResult(null);
        try {
            const res = await api.get(`/tools/subnet-calc?cidr=${encodeURIComponent(cidr)}`);
            setResult(res.data);
        } catch (err) {
            setError(err.response?.data?.detail || 'Error en cálculo');
        } finally {
            setLoading(false);
        }
    };

    return (
        <Card className="p-6">
            <h3 className="text-xl font-bold mb-4 flex items-center gap-2">
                <Calculator className="w-5 h-5 text-blue-500" />
                Calculadora de Subredes
            </h3>
            <div className="flex gap-2 mb-4">
                <input 
                    type="text" 
                    placeholder="Ej: 192.168.1.0/24" 
                    value={cidr}
                    onChange={(e) => setCidr(e.target.value)}
                    className="flex-1 bg-dark-bg-secondary border border-dark-border-primary rounded-lg px-4 py-2 text-dark-text-primary focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <Button onClick={calculate} disabled={loading}>{loading ? '...' : 'Calcular'}</Button>
            </div>
            
            {error && <div className="text-red-400 text-sm mb-4">{error}</div>}
            
            {result && (
                <div className="grid grid-cols-2 gap-4 text-sm">
                    <div className="p-3 bg-dark-bg-tertiary rounded-lg">
                        <span className="block text-dark-text-muted text-xs">Máscara</span>
                        <span className="font-mono text-dark-text-primary">{result.netmask}</span>
                    </div>
                    <div className="p-3 bg-dark-bg-tertiary rounded-lg">
                        <span className="block text-dark-text-muted text-xs">Total Hosts</span>
                        <span className="font-mono text-dark-text-primary">{result.total_hosts}</span>
                    </div>
                     <div className="p-3 bg-dark-bg-tertiary rounded-lg">
                        <span className="block text-dark-text-muted text-xs">Primer Host</span>
                        <span className="font-mono text-dark-text-primary">{result.first_host}</span>
                    </div>
                     <div className="p-3 bg-dark-bg-tertiary rounded-lg">
                        <span className="block text-dark-text-muted text-xs">Último Host</span>
                        <span className="font-mono text-dark-text-primary">{result.last_host}</span>
                    </div>
                    <div className="p-3 bg-dark-bg-tertiary rounded-lg col-span-2">
                        <span className="block text-dark-text-muted text-xs">Broadcast</span>
                        <span className="font-mono text-dark-text-primary">{result.broadcast_address}</span>
                    </div>
                </div>
            )}
        </Card>
    );
};

const MacLookup = () => {
    const [mac, setMac] = useState('');
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);

    const lookup = async () => {
        setLoading(true);
        setResult(null);
        try {
            const res = await api.get(`/tools/mac-lookup?mac=${encodeURIComponent(mac)}`);
            setResult(res.data);
        } catch (err) {
            setResult({ company: 'Error', error: 'No se pudo consultar' });
        } finally {
            setLoading(false);
        }
    };

    return (
        <Card className="p-6">
            <h3 className="text-xl font-bold mb-4 flex items-center gap-2">
                <Search className="w-5 h-5 text-purple-500" />
                Buscador MAC (OUI)
            </h3>
             <div className="flex gap-2 mb-4">
                <input 
                    type="text" 
                    placeholder="Ej: 00:0c:29:4f:8e:35" 
                    value={mac}
                    onChange={(e) => setMac(e.target.value)}
                    className="flex-1 bg-dark-bg-secondary border border-dark-border-primary rounded-lg px-4 py-2 text-dark-text-primary focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <Button onClick={lookup} disabled={loading}>{loading ? '...' : 'Buscar'}</Button>
            </div>
            
             {result && (
                <div className="p-4 bg-dark-bg-tertiary rounded-lg border border-dark-border-primary">
                    {result.error ? (
                         <div className="flex items-center gap-2 text-red-400">
                            <AlertCircle className="w-4 h-4" />
                            <span>{result.error}</span>
                         </div>
                    ) : (
                        <div className="flex flex-col">
                            <span className="text-dark-text-muted text-xs uppercase tracking-wider mb-1">Fabricante</span>
                            <span className="text-lg font-semibold text-dark-text-primary">{result.company}</span>
                            <span className="text-dark-text-muted text-xs mt-2">{result.address}</span>
                        </div>
                    )}
                </div>
            )}
        </Card>
    );
};

const DNSLookup = () => {
    const [domain, setDomain] = useState('');
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);

    const lookup = async () => {
        setLoading(true);
        setResult(null);
        try {
            const res = await api.get(`/tools/dns-lookup?domain=${encodeURIComponent(domain)}`);
            setResult(res.data);
        } catch (err) {
             setResult({ error: 'Error al consultar DNS' });
        } finally {
            setLoading(false);
        }
    };

    return (
        <Card className="p-6">
            <h3 className="text-xl font-bold mb-4 flex items-center gap-2">
                <Network className="w-5 h-5 text-green-500" />
                DNS Records
            </h3>
             <div className="flex gap-2 mb-4">
                <input 
                    type="text" 
                    placeholder="Ej: google.com" 
                    value={domain}
                    onChange={(e) => setDomain(e.target.value)}
                    className="flex-1 bg-dark-bg-secondary border border-dark-border-primary rounded-lg px-4 py-2 text-dark-text-primary focus:outline-none focus:ring-2 focus:ring-green-500"
                />
                <Button onClick={lookup} disabled={loading}>{loading ? '...' : 'Consultar'}</Button>
            </div>
            
             {result && !result.error && (
                <div className="overflow-x-auto">
                    <table className="w-full text-sm text-left">
                        <thead className="text-xs text-dark-text-muted uppercase bg-dark-bg-tertiary">
                            <tr>
                                <th className="px-3 py-2 rounded-tl-lg">Tipo</th>
                                <th className="px-3 py-2 rounded-tr-lg">Valor</th>
                            </tr>
                        </thead>
                        <tbody>
                            {result.records.map((rec, idx) => (
                                <tr key={idx} className="border-b border-dark-border-primary/30 last:border-0 hover:bg-dark-bg-tertiary/50">
                                    <td className="px-3 py-2 font-mono text-green-400 font-bold">{rec.type}</td>
                                    <td className="px-3 py-2 font-mono text-dark-text-secondary truncate max-w-xs" title={rec.value}>{rec.value}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {result.records.length === 0 && <p className="text-center text-dark-text-muted mt-2">No records found</p>}
                </div>
            )}
        </Card>
    );
};


export default function ToolsPage() {
    return (
        <div className="container-app py-8">
            <h2 className="text-2xl font-bold text-dark-text-primary mb-2">Herramientas de Red</h2>
            <p className="text-dark-text-muted mb-8">Utilidades rápidas para diagnóstico y cálculo.</p>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                <SubnetCalculator />
                <MacLookup />
                <DNSLookup />
            </div>
        </div>
    )
}
