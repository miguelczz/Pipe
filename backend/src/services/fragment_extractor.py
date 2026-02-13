"""
Specialized service for extracting relevant fragments from PCAP files.
Its sole responsibility is to isolate time ranges using tshark so other
components can consume them.
"""
import os
import subprocess
import shutil
from typing import List, Optional
from pathlib import Path

from ..models.btm_schemas import CaptureFragment

class FragmentExtractor:
    """
    Extracts network capture fragments using tshark.
    Allows visualizing specific events without having to open 100MB+ captures.
    """

    def __init__(self, output_base_dir: str = "data/fragments"):
        # Ensure the base directory is absolute
        base_path = Path(output_base_dir)
        if not base_path.is_absolute():
            # If relative, resolve it from the current working directory
            base_path = Path(output_base_dir).resolve()
        self.output_base_dir = base_path
        self.tshark_path = shutil.which("tshark")
        
        # Ensure the output directory exists
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
        Extracts a specific time range from a capture.
        Adds a margin (padding) before and after for context.
        """
        if not self.tshark_path:
            return None

        # Configure paths
        input_path = Path(input_file)
        if not input_path.exists():
            return None

        output_filename = f"{output_name}_{int(start_time)}.pcap"
        output_path = self.output_base_dir / output_filename

        # Adjust times with padding
        t_start = start_time - padding_seconds
        t_end = end_time + padding_seconds

        # tshark command to filter by time
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
            
            # Get packet count from the fragment
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
        Extracts specifically a BTM sequence (Request -> Response -> Association).
        """
        return self.extract_time_range(
            input_file=input_file,
            start_time=request_time,
            end_time=request_time + 3.0, # We assume 3 seconds for the complete sequence
            output_name=f"btm_{client_mac.replace(':', '')}",
            description=f"BTM sequence for client {client_mac}",
            padding_seconds=0.5
        )

    def extract_channel_transition(self, input_file: str, client_mac: str, transition_time: float) -> Optional[CaptureFragment]:
        """
        Extracts the fragment where the channel/band change is seen.
        """
        return self.extract_time_range(
            input_file=input_file,
            start_time=transition_time,
            end_time=transition_time + 1.0,
            output_name=f"steer_{client_mac.replace(':', '')}",
            description=f"Channel/band change for client {client_mac}",
            padding_seconds=1.5 # More margin to see traffic before and after
        )
