"""
Servicio especializado para la extracción de fragmentos relevantes de archivos PCAP.
Permite aislar eventos específicos como cambios de canal, secuencias BTM o fallos.
"""
import logging
import os
import subprocess
import shutil
from typing import List, Optional
from pathlib import Path

from ..models.btm_schemas import CaptureFragment

logger = logging.getLogger(__name__)

class FragmentExtractor:
    """
    Extrae fragmentos de captura de red usando tshark.
    Permite visualizar eventos específicos sin tener que abrir capturas de 100MB+.
    """

    def __init__(self, output_base_dir: str = "data/fragments"):
        # Asegurar que el directorio base sea absoluto
        base_path = Path(output_base_dir)
        if not base_path.is_absolute():
            # Si es relativo, resolverlo desde el directorio de trabajo actual
            base_path = Path(output_base_dir).resolve()
        self.output_base_dir = base_path
        self.tshark_path = shutil.which("tshark")
        
        # Asegurar que el directorio de salida existe
        self.output_base_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.tshark_path:
            pass

    def extract_time_range(
        self, 
        input_file: str, 
        start_time: float, 
        end_time: float, 
        output_name: str,
        description: str,
        padding_seconds: float = 1.0
    ) -> Optional[CaptureFragment]:
        """
        Extrae un rango de tiempo específico de una captura.
        Agrega un margen (padding) antes y después para contexto.
        """
        if not self.tshark_path:
            return None

        # Configurar rutas
        input_path = Path(input_file)
        if not input_path.exists():
            return None

        output_filename = f"{output_name}_{int(start_time)}.pcap"
        output_path = self.output_base_dir / output_filename

        # Ajustar tiempos con padding
        t_start = start_time - padding_seconds
        t_end = end_time + padding_seconds

        # Comando tshark para filtrar por tiempo
        # -Y (display filter) usando frame.time_epoch
        filter_str = f"frame.time_epoch >= {t_start} && frame.time_epoch <= {t_end}"
        
        cmd = [
            self.tshark_path,
            "-r", str(input_path),
            "-Y", filter_str,
            "-w", str(output_path)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Obtener conteo de paquetes del fragmento
            count_cmd = [self.tshark_path, "-r", str(output_path), "-T", "fields", "-e", "frame.number"]
            count_result = subprocess.run(count_cmd, capture_output=True, text=True)
            packet_count = len(count_result.stdout.splitlines())

            return CaptureFragment(
                fragment_id=f"frag_{int(start_time)}",
                fragment_type="time_range",
                description=description,
                start_time=t_start,
                end_time=t_end,
                packet_count=packet_count,
                file_path=str(output_path.absolute()),
                download_url=f"/api/files/fragments/{output_filename}"
            )

        except subprocess.CalledProcessError as e:
            return None
        except Exception as e:
            return None

    def extract_btm_sequence(self, input_file: str, client_mac: str, request_time: float) -> Optional[CaptureFragment]:
        """
        Extrae específicamente una secuencia BTM (Request -> Response -> Association).
        """
        return self.extract_time_range(
            input_file=input_file,
            start_time=request_time,
            end_time=request_time + 3.0, # Asumimos 3 segundos para la secuencia completa
            output_name=f"btm_{client_mac.replace(':', '')}",
            description=f"Secuencia BTM para cliente {client_mac}",
            padding_seconds=0.5
        )

    def extract_channel_transition(self, input_file: str, client_mac: str, transition_time: float) -> Optional[CaptureFragment]:
        """
        Extrae el fragmento donde se ve el cambio de canal/banda.
        """
        return self.extract_time_range(
            input_file=input_file,
            start_time=transition_time,
            end_time=transition_time + 1.0,
            output_name=f"steer_{client_mac.replace(':', '')}",
            description=f"Cambio de canal/banda para cliente {client_mac}",
            padding_seconds=1.5 # Más margen para ver el tráfico antes y después
        )
