"""
Pydantic schemas for Band Steering analysis.
Data structure definitions for 802.11 events, BTM, metrics and reports.
"""
from enum import Enum
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field


# ============================================================================
# Enums and Constants
# ============================================================================

class BTMStatusCode(str, Enum):
    """
    BTM status codes according to 802.11v standard.
    Defines the client response to a transition request.
    """
    ACCEPT = "0"
    ACCEPT_PREFERRED = "1"
    REJECT_UNSPECIFIED = "2"
    REJECT_INSUFFICIENT_BEACON = "3"
    REJECT_INSUFFICIENT_CAPINFO = "4"
    REJECT_UNACCEPTABLE_DELAY = "5"
    REJECT_DESTINATION_UNREACHABLE = "6"
    REJECT_INVALID_CANDIDATE = "7"
    REJECT_LEAVING_ESS = "8"
    UNKNOWN = "unknown"

    @classmethod
    def is_success(cls, code: Union[str, int]) -> bool:
        """Determines if a code represents a successful transition (0 or 1)."""
        str_code = str(code)
        return str_code in [cls.ACCEPT.value, cls.ACCEPT_PREFERRED.value]

    @classmethod
    def get_description(cls, code: Union[str, int]) -> str:
        """Gets the readable description of the code according to table 9-428."""
        descriptions = {
            "0": "Accept",
            "1": "Reject - Unspecified reject reason",
            "2": "Reject - Insufficient Beacon or Probe Response",
            "3": "Reject - Insufficient available capacity",
            "4": "Reject - BSS termination undesired",
            "5": "Reject - BSS termination delay requested",
            "6": "Reject - STA BSS Transition Candidate List provided",
            "7": "Reject - No suitable BSS transition candidates",
            "8": "Reject - Leaving ESS",
        }
        return descriptions.get(str(code), f"Code {code}")


class SteeringType(str, Enum):
    """
    Types of steering patterns detected.
    """
    AGGRESSIVE = "aggressive"  # Deauth/Disassoc forzada
    ASSISTED = "assisted"      # BTM, 802.11v
    PREVENTIVE = "preventive"  # Preventive steering before degradation
    UNKNOWN = "unknown"


class DeviceCategory(str, Enum):
    """
    Device categories based on OUI and behavior.
    """
    MOBILE = "mobile_device"
    COMPUTER = "computer_laptop"
    NETWORK_EQUIPMENT = "network_equipment"
    VIRTUAL_MACHINE = "virtual_machine"
    IOT_DEVICE = "iot_device"
    UNKNOWN = "unknown_device"


# ============================================================================
# Component Models
# ============================================================================

class DeviceInfo(BaseModel):
    """Detailed information of an analyzed device."""
    mac_address: str = Field(..., description="Device MAC address")
    oui: str = Field(..., description="OUI (first 6 characters)")
    vendor: str = Field(..., description="Identified manufacturer")
    device_model: Optional[str] = Field(None, description="Device model (if detectable)")
    device_category: DeviceCategory = Field(default=DeviceCategory.UNKNOWN, description="Device category")
    is_virtual: bool = Field(False, description="Indicates if it is a virtual machine or random MAC")
    confidence_score: float = Field(0.0, ge=0.0, le=1.0, description="Identification confidence (0-1)")


class BTMEvent(BaseModel):
    """Individual event related to BSS Transition Management (802.11v)."""
    timestamp: float = Field(..., description="Event timestamp in the capture")
    event_type: str = Field(..., description="Event type: 'request' or 'response'")
    client_mac: str = Field(..., description="MAC of the involved client")
    ap_bssid: str = Field(..., description="BSSID of the involved AP")
    status_code: Optional[int] = Field(None, description="BTM status code (only for responses)")
    band: Optional[str] = Field(None, description="Frequency band (2.4GHz/5GHz)")
    frequency: Optional[int] = Field(None, description="Frequency in MHz")
    rssi: Optional[int] = Field(None, description="Signal strength (dBm)")
    # Additional context fields
    frame_number: Optional[int] = Field(None, description="Wireshark frame number")


class SteeringTransition(BaseModel):
    """
    Represents a complete roaming/steering transition.
    """
    client_mac: str = Field(..., description="Client MAC")
    steering_type: SteeringType = Field(default=SteeringType.UNKNOWN, description="Type of steering mechanism used")
    
    # Timing
    start_time: float = Field(..., description="Transition start (e.g., first BTM Request or Deauth)")
    end_time: Optional[float] = Field(None, description="Transition end (e.g., Reassociation Complete)")
    duration: Optional[float] = Field(None, description="Duration in seconds")
    
    # Source and Destination
    from_bssid: Optional[str] = Field(None, description="Source BSSID")
    to_bssid: Optional[str] = Field(None, description="Destination BSSID")
    from_band: Optional[str] = Field(None, description="Source band")
    to_band: Optional[str] = Field(None, description="Destination band")
    
    # Transition status
    is_successful: bool = Field(..., description="Was the transition completed successfully?")
    is_band_change: bool = Field(False, description="Was there a band change (e.g., 2.4 -> 5)?")
    returned_to_original: bool = Field(False, description="Did the client return to the original AP (ping-pong)?")
    
    # Technical details
    btm_status_code: Optional[int] = Field(None, description="Associated BTM code if applicable")
    failure_reason: Optional[str] = Field(None, description="Failure reason if not successful")


class KVRSupport(BaseModel):
    """Evaluation of standards 802.11k/v/r."""
    k_support: bool = Field(False, description="802.11k support (Radio Measurement)")
    v_support: bool = Field(False, description="802.11v support (BTM/WNM)")
    r_support: bool = Field(False, description="802.11r support (Fast Transition)")


class ComplianceCheck(BaseModel):
    """
    Individual compliance check (e.g., 'BTM Support', 'No Loops').
    Used to generate the summary table.
    """
    check_name: str = Field(..., description="Short name of the verification")
    description: str = Field(..., description="Detailed description")
    category: str = Field(..., description="Category: 'btm', 'kvr', 'association', 'performance'")
    passed: bool = Field(..., description="Did it pass the test?")
    severity: str = Field(..., description="Severity: 'low', 'medium', 'high', 'critical'")
    details: Optional[str] = Field(None, description="Technical details (e.g., 'Requests: 5, Resp: 0')")
    recommendation: Optional[str] = Field(None, description="Suggested action if failed")


class CaptureFragment(BaseModel):
    """
    Metadata of an extracted capture fragment (e.g., roaming pcap).
    """
    fragment_id: str = Field(..., description="Unique fragment identifier")
    fragment_type: str = Field(..., description="Type: 'btm_sequence', 'transition', 'channel_change'")
    description: str = Field(..., description="Human description of the fragment")
    start_time: float = Field(..., description="Start timestamp")
    end_time: float = Field(..., description="End timestamp")
    packet_count: int = Field(0, description="Number of packets in the fragment")
    file_path: Optional[str] = Field(None, description="Absolute path to the generated file")
    download_url: Optional[str] = Field(None, description="Relative URL for download")


# ============================================================================
# Main Analysis Model
# ============================================================================

class SignalSample(BaseModel):
    timestamp: float = Field(..., description="Packet timestamp")
    rssi: int = Field(..., description="Signal strength (dBm)")
    band: str = Field(..., description="Band (2.4GHz/5GHz)")
    frequency: int = Field(..., description="Frequency in MHz")


class BandSteeringAnalysis(BaseModel):
    """
    Root object that contains ALL results of a capture analysis.
    """
    analysis_id: str = Field(..., description="Analysis UUID")
    filename: str = Field(..., description="Original pcap filename")
    analysis_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Analysis date")
    
    # Global Metrics
    total_packets: int = Field(0, description="Total packets analyzed")
    wlan_packets: int = Field(0, description="Total WiFi packets")
    analysis_duration_ms: int = Field(0, description="Analysis time (ms)")
    
    # Identified Devices
    devices: List[DeviceInfo] = Field(default_factory=list, description="List of analyzed unique devices")
    
    # Events and Transitions
    btm_events: List[BTMEvent] = Field(default_factory=list, description="Flat list of BTM events")
    transitions: List[SteeringTransition] = Field(default_factory=list, description="List of detected transitions")
    signal_samples: List[SignalSample] = Field(default_factory=list, description="Signal samples over time")
    
    # Aggregate Metrics
    btm_requests: int = Field(0, description="Total Requests")
    btm_responses: int = Field(0, description="Total Responses")
    btm_success_rate: float = Field(0.0, ge=0.0, le=1.0, description="Success rate (Responses 0/1 over Total)")
    
    successful_transitions: int = Field(0, description="Total successful transitions")
    failed_transitions: int = Field(0, description="Total failed transitions")
    
    loops_detected: bool = Field(False, description="Was band ping-pong detected?")
    
    # Compliance and Support
    kvr_support: KVRSupport = Field(default_factory=KVRSupport, description="KVR support summary")
    compliance_checks: List[ComplianceCheck] = Field(default_factory=list, description="List of checks for the summary table")
    
    # Final Result
    verdict: str = Field(..., description="Final verdict: 'SUCCESS', 'PARTIAL', 'FAILED', 'NO_DATA'")
    analysis_text: Optional[str] = Field(None, description="Narrative report generated by AI")
    
    # Complete Raw Data (for UI reconstruction)
    raw_stats: Optional[Dict[str, Any]] = Field(None, description="Complete Wireshark stats (diagnostics, steering_analysis, etc.)")
    
    # Fragments
    fragments: List[CaptureFragment] = Field(default_factory=list, description="Extracted pcap fragments")

    class Config:
        use_enum_values = True
