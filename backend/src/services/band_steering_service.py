"""
Main orchestrator service for Band Steering analysis.

This class coordinates the high-level flow of Band Steering analysis:
- Uses `WiresharkTool` to extract raw data from the capture.
- Uses `BTMAnalyzer` for specialized BTM analysis and compliance.
- Uses `DeviceClassifier` to identify the device.
- Uses `FragmentExtractor` to extract relevant fragments from the capture.
- Handles results persistence and indexing for RAG.

All specific domain logic is delegated to these specialized components.
"""
import json
import os
import shutil
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..tools.wireshark_tool import WiresharkTool
from ..tools.btm_analyzer import BTMAnalyzer
from ..tools.device_classifier import DeviceClassifier
from .fragment_extractor import FragmentExtractor
from .embeddings_service import process_and_store_pdf  # Para indexar si generamos PDF
from ..models.btm_schemas import BandSteeringAnalysis, DeviceInfo
from ..repositories.qdrant_repository import get_qdrant_repository


class BandSteeringService:
    """
    Orchestra director for the Band Steering process.

    Limited to coordinating specialized components, without reimplementing their
    internal analysis or extraction logic.
    """

    def __init__(
        self, 
        base_data_dir: str = "data/analyses",
        wireshark_tool: Optional[WiresharkTool] = None,
        btm_analyzer: Optional[BTMAnalyzer] = None,
        device_classifier: Optional[DeviceClassifier] = None,
        fragment_extractor: Optional[FragmentExtractor] = None
    ):
        # Ensure the base directory is absolute
        # In Docker, use /app/data/analyses; in local, use resolved relative path
        base_path = Path(base_data_dir)
        if not base_path.is_absolute():
            # If relative, resolve it from the current working directory
            # In Docker, WORKDIR is /app, so "data/analyses" resolves to /app/data/analyses
            # In local, it resolves from where the script is executed
            base_path = Path(base_data_dir).resolve()
        self.base_dir = base_path
        self.wireshark_tool = wireshark_tool or WiresharkTool()
        self.btm_analyzer = btm_analyzer or BTMAnalyzer()
        self.device_classifier = device_classifier or DeviceClassifier()
        self.fragment_extractor = fragment_extractor or FragmentExtractor()
        
        # Create base directory if it doesn't exist
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def process_capture(
        self, 
        file_path: str, 
        user_metadata: Optional[Dict[str, str]] = None,
        original_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes the complete Band Steering analysis cycle:
        extraction → classification → BTM analysis → fragmentation → AI report → persistence → indexing.
        """
        file_name = original_filename or os.path.basename(file_path)
        
        # 1. Raw data extraction (WiresharkTool)
        ssid_hint = (user_metadata or {}).get("ssid") if user_metadata else None
        client_mac_hint = (user_metadata or {}).get("client_mac") if user_metadata else None
        raw_data = self.wireshark_tool._extract_basic_stats(
            file_path=file_path,
            ssid_filter=ssid_hint,
            client_mac_hint=client_mac_hint,
        )
        
        # 2. Identification and Classification of the Device
        device_info = self._determine_primary_mac_and_device(
            raw_data=raw_data,
            user_metadata=user_metadata,
            file_name=file_name,
            client_mac_hint=client_mac_hint,
        )

        # 3. Specialized BTM analysis and compliance (BTMAnalyzer)
        analysis = self._run_btm_analysis(raw_data, file_name, device_info)

        # 4. Fragment Extraction (FragmentExtractor)
        analysis.fragments = self._extract_fragments(analysis, file_path)

        # 5. Narrative Report Generation (AI)
        technical_summary = self._build_technical_summary_and_verdict(
            raw_data=raw_data,
            file_name=file_name,
            analysis=analysis,
        )
        analysis.analysis_text = self.wireshark_tool._ask_llm_for_analysis(technical_summary)

        # 6. Save user_metadata in raw_data for persistence
        self._attach_user_metadata(raw_data, user_metadata)

        # 7. Save raw_stats in the analysis object for persistence
        analysis.raw_stats = raw_data

        # 8. Organization, persistence, and indexing
        save_path = self._persist_analysis(analysis, device_info, file_path)
        self._index_analysis_for_rag(analysis)

        # Return analysis object and raw data (for frontend compatibility)
        return {
            "analysis": analysis,
            "raw_stats": raw_data,
            "save_path": save_path,
        }

    def _determine_primary_mac_and_device(
        self,
        raw_data: Dict[str, Any],
        user_metadata: Optional[Dict[str, str]],
        file_name: str,
        client_mac_hint: Optional[str],
    ) -> DeviceInfo:
        """
        Determines the primary client MAC and returns the device classification
        using `DeviceClassifier`. Contains MAC validation and fallback logic.
        """
        steering_events = raw_data.get("steering_events", [])

        def is_valid_client_mac(mac: str) -> bool:
            if not mac or mac == "ff:ff:ff:ff:ff:ff" or mac == "00:00:00:00:00:00":
                return False
            try:
                first_octet = int(mac.split(":")[0], 16)
                # Multicast bit should not be active
                if first_octet & 1:
                    return False
            except Exception:
                return False
            return True

        primary_mac = "unknown"

        # Get known BSSIDs for validation
        bssid_info = raw_data.get("diagnostics", {}).get("bssid_info", {})
        known_bssids = set()
        if bssid_info:
            for bssid in bssid_info.keys():
                if bssid:
                    known_bssids.add(bssid.lower().replace("-", ":"))

        # Prefer the MAC provided by the user if valid
        if client_mac_hint and is_valid_client_mac(client_mac_hint):
            hint_normalized = client_mac_hint.lower().replace("-", ":")
            # If it's a known BSSID, we don't use it as client MAC
            if hint_normalized not in known_bssids:
                primary_mac = client_mac_hint
        else:
            # Try to get it from steering events
            for event in steering_events:
                event_mac = event.get("client_mac")
                if is_valid_client_mac(event_mac):
                    primary_mac = event_mac
                    break

            # If no specific events, use the one detected by WiresharkTool as global
            if primary_mac == "unknown":
                primary_mac = raw_data.get("diagnostics", {}).get("client_mac", "unknown")

        # Validate that primary_mac is a valid MAC before classifying.
        # If not valid, use a generic valid MAC to avoid errors in classify_device.
        if not is_valid_client_mac(primary_mac) or primary_mac == "unknown":
            # Use a generic valid MAC (unicast, globally administered)
            primary_mac = "00:11:22:33:44:55"

        return self.device_classifier.classify_device(
            primary_mac,
            user_metadata,
            filename=file_name,
        )

    def _extract_fragments(
        self,
        analysis: BandSteeringAnalysis,
        file_path: str,
    ) -> List[Any]:
        """
        Extracts relevant fragments from the capture for each transition with band change.
        Returns the list of generated `CaptureFragment`.
        """
        fragments: List[Any] = []
        for transition in analysis.transitions:
            if transition.is_band_change:
                frag = self.fragment_extractor.extract_channel_transition(
                    input_file=file_path,
                    client_mac=transition.client_mac,
                    transition_time=transition.start_time,
                )
                if frag:
                    fragments.append(frag)
        return fragments

    def _run_btm_analysis(
        self,
        raw_data: Dict[str, Any],
        file_name: str,
        device_info: DeviceInfo,
    ) -> BandSteeringAnalysis:
        """
        Encapsulates the preparation of `band_counters` and the call to `BTMAnalyzer`,
        updating auxiliary structures of `raw_data` to maintain metric consistency
        across the entire system.
        """
        steering_events = raw_data.get("steering_events", [])
        signal_samples = raw_data.get("signal_samples", [])

        # Synchronize: Pass WiresharkTool results as base for BTMAnalyzer.
        combined_stats = raw_data.get("diagnostics", {}).get("band_counters", {}).copy()
        if "steering_analysis" in raw_data:
            combined_stats.update(raw_data["steering_analysis"])

        wireshark_raw = raw_data.get("diagnostics", {}).get("wireshark_raw")
        if wireshark_raw:
            combined_stats["wireshark_raw"] = wireshark_raw

        analysis = self.btm_analyzer.analyze_btm_events(
            steering_events=steering_events,
            band_counters=combined_stats,
            filename=file_name,
            device_info=device_info,
            signal_samples=signal_samples,
            wireshark_raw=wireshark_raw,
        )

        # SYNCHRONIZE: Update steering_analysis with the values calculated in
        # BTMAnalyzer so that all panels show the same values.
        # In this direction, BTMAnalyzer can only *refine* values already
        # derived from WiresharkTool, but never invent counters that
        # contradict `wireshark_raw.summary`.
        primary_mac = device_info.mac_address
        if "steering_analysis" in raw_data:
            synchronized_metrics = self._synchronize_steering_metrics(
                analysis,
                steering_events,
                primary_client_mac=primary_mac,
            )
            raw_data["steering_analysis"].update(synchronized_metrics)

        # COMPARE: Raw Wireshark vs Processed Data
        wireshark_compare = self._compare_wireshark_raw_vs_processed(
            wireshark_raw,
            raw_data.get("steering_analysis", {}),
            analysis,
        )
        if "diagnostics" in raw_data:
            raw_data["diagnostics"]["wireshark_compare"] = wireshark_compare

        # Complete global data that BTMAnalyzer does not have
        analysis.total_packets = raw_data.get("total_packets", 0)
        analysis.wlan_packets = raw_data.get("total_wlan_packets", 0)

        return analysis

    def _build_technical_summary_and_verdict(
        self,
        raw_data: Dict[str, Any],
        file_name: str,
        analysis: BandSteeringAnalysis,
    ) -> str:
        """
        Builds the `technical_summary` for the LLM and recalculates the verdict
        based on compliance checks, keeping all business logic related to the report
        in one place.
        """
        # We use WiresharkTool logic to maintain consistency with the visual report
        technical_summary = self.wireshark_tool._build_technical_summary(
            stats=raw_data,
            file_name=file_name,
        )

        # Recalculate the verdict based on corrected checks.
        corrected_verdict = self.btm_analyzer._determine_verdict(
            checks=analysis.compliance_checks,
            transitions=analysis.transitions,
            btm_rate=analysis.btm_success_rate,
            success_count=analysis.successful_transitions,
        )
        analysis.verdict = corrected_verdict

        # Add compliance info to summary for the LLM
        technical_summary += "\n\n## COMPLIANCE AUDIT (BAND STEERING)\n\n"
        technical_summary += f"**Final Verdict:** {analysis.verdict}\n\n"

        # Add explicit information about band changes correctly calculated BEFORE the checks
        # so the agent has clear context from the start
        steering_check = next(
            (c for c in analysis.compliance_checks if c.check_name == "Steering Efectivo"),
            None,
        )
        if steering_check:
            details = steering_check.details or ""
            band_change_match = re.search(
                r"BAND CHANGE TRANSITIONS:\s*(\d+)", details
            )
            total_match = re.search(r"TOTAL TRANSITIONS:\s*(\d+)", details)
            btm_match = re.search(r"BTM ACCEPT:\s*(\d+)", details)

            if band_change_match:
                band_change_count = int(band_change_match.group(1))
                total_transitions = int(total_match.group(1)) if total_match else 0
                btm_accept = int(btm_match.group(1)) if btm_match else 0

                technical_summary += (
                    "### 📊 EFFECTIVE STEERING SUMMARY (CORRECTED VALUES)\n\n"
                )
                technical_summary += (
                    "**⚠️ IMPORTANT:** The following values were calculated "
                    "comparing consecutive transitions to detect real band "
                    "changes, even if the individual `is_band_change` field "
                    "was not correctly marked.\n\n"
                )
                technical_summary += (
                    f"- **Physical band changes detected:** {band_change_count}\n"
                )
                technical_summary += (
                    f"- **Total successful transitions:** {total_transitions}\n"
                )
                technical_summary += (
                    f"- **BTM Accept (Status Code 0):** {btm_accept}\n\n"
                )
                technical_summary += (
                    f"**CRITICAL NOTE:** The number of band changes ({band_change_count}) "
                    "is the CORRECT value calculated by comparing consecutive "
                    "transitions. This is the value that should be used to determine if the "
                    "steering was effective, NOT the number that may appear in other "
                    "sections of the summary.\n\n"
                )

        # Separate checks into passed and failed for clarity
        passed_checks = [c for c in analysis.compliance_checks if c.passed]
        failed_checks = [c for c in analysis.compliance_checks if not c.passed]

        if failed_checks:
            technical_summary += "### ❌ FAILED CHECKS (CAUSE OF VERDICT):\n"
            for check in failed_checks:
                technical_summary += f"- **{check.check_name}**: FAILED\n"
                technical_summary += f"  - Description: {check.description}\n"
                technical_summary += f"  - Evidence: {check.details}\n"
                if check.recommendation:
                    technical_summary += (
                        f"  - Recommendation: {check.recommendation}\n"
                    )
                technical_summary += "\n"

        if passed_checks:
            technical_summary += "### ✅ PASSED CHECKS:\n"
            for check in passed_checks:
                technical_summary += (
                    f"- **{check.check_name}**: PASSED ({check.details})\n"
                )

        # Verdict explanation based on failures
        technical_summary += (
            f"\n**ROOT CAUSE OF VERDICT '{analysis.verdict}':**\n"
        )
        if analysis.verdict == "FAILED":
            if failed_checks:
                technical_summary += (
                    "The test failed due to the following critical issues:\n"
                )
                for check in failed_checks:
                    technical_summary += (
                        f"  - {check.check_name}: "
                        f"{check.recommendation or 'Review configuration'}\n"
                    )
            else:
                technical_summary += (
                    "General failure without specific identified checks.\n"
                )
        elif analysis.verdict == "SUCCESS":
            technical_summary += (
                "The test was successful: band steering criteria were met.\n"
            )
            if steering_check and steering_check.passed:
                band_change_match = re.search(
                    r"BAND CHANGE TRANSITIONS:\s*(\d+)",
                    steering_check.details or "",
                )
                if band_change_match:
                    band_change_count = int(band_change_match.group(1))
                    technical_summary += (
                        f"{band_change_count} successful band change(s) detected, "
                        "meeting the minimum required criteria.\n"
                    )

        return technical_summary

    @staticmethod
    def _attach_user_metadata(
        raw_data: Dict[str, Any],
        user_metadata: Optional[Dict[str, str]],
    ) -> None:
        """
        Inserts user metadata (SSID, client_mac, etc.) within the 
        `raw_data["diagnostics"]["user_metadata"]` structure for persistence.
        """
        if not user_metadata:
            return

        diagnostics = raw_data.setdefault("diagnostics", {})
        user_meta = diagnostics.setdefault("user_metadata", {})

        ssid = user_metadata.get("ssid")
        client_mac = user_metadata.get("client_mac")

        if ssid:
            user_meta["ssid"] = ssid
        if client_mac:
            user_meta["client_mac"] = client_mac


    def _synchronize_steering_metrics(
        self, 
        analysis: BandSteeringAnalysis, 
        steering_events: List[Dict[str, Any]],
        primary_client_mac: str
    ) -> Dict[str, Any]:
        """
        Synchronizes steering_analysis metrics with values calculated in BTMAnalyzer.
        This ensures that all panels (metrics, compliance checks, chart) show the same values.
        
        Uses the SAME logic as compliance checks to ensure consistency.
        """
        # USE EXACTLY THE SAME LOGIC as compliance checks to ensure consistency
        
        # Count successful band change transitions
        band_change_transitions = sum(1 for t in analysis.transitions if t.is_successful and t.is_band_change)
        
        # Count successful transitions between different BSSIDs (roaming within the same band)
        # SAME CRITERIA as compliance checks: only BSSID changes, not all transitions without band change
        bssid_change_transitions = sum(
            1
            for t in analysis.transitions
            if t.is_successful
            and t.from_bssid
            and t.to_bssid
            and t.from_bssid != t.to_bssid
        )
        
        # Count successful BTM responses (client cooperation with steering)
        btm_successful_responses = sum(
            1 for e in steering_events 
            if e.get("type") == "btm" 
            and e.get("event_type") == "response"
            and (e.get("status_code") == 0 or str(e.get("status_code")) == "0")
            and (not primary_client_mac or e.get("client_mac") == primary_client_mac)
        )
        
        # SAME CRITERIA as compliance checks: Effective steering ONLY if there is:
        # 1. At least 1 successful band change, OR
        # 2. At least 1 successful transition between different BSSIDs
        # NOTE: BTM Accept only counts if there is also band or BSSID change
        # (a BTM Accept without physical change is not effective steering)
        # CORRECTION: Count ALL successful transitions (not just the max)
        # A transition can have band change AND BSSID change, but only counts once
        total_successful_transitions = sum(1 for t in analysis.transitions if t.is_successful)
        steering_effective_count = max(band_change_transitions, bssid_change_transitions)
        
        # If there is BTM Accept BUT there is also band/BSSID change, it is effective steering
        # If there is only BTM Accept without physical changes, it is NOT effective steering
        if btm_successful_responses > 0 and steering_effective_count == 0:
            # BTM Accept without physical change: not effective steering
            total_successful = 0
        else:
            # Use total successful transitions (not just the max between types)
            # This ensures all are counted: band changes + association transitions
            total_successful = total_successful_transitions
        
        # Count BTM requests for the primary client
        btm_requests_count = sum(
            1 for e in steering_events 
            if e.get("type") == "btm" 
            and e.get("event_type") == "request"
            and (not primary_client_mac or e.get("client_mac") == primary_client_mac)
        )
        
        # Total attempts is the max between BTM requests and number of transitions
        # This ensures that if there are more transitions than requests, all are counted
        total_attempts = max(btm_requests_count, len(analysis.transitions))
        
        # Calculate average time of successful transitions
        successful_transition_times = [
            t.duration for t in analysis.transitions 
            if t.is_successful and t.duration and t.duration > 0
        ]
        avg_time = sum(successful_transition_times) / len(successful_transition_times) if successful_transition_times else 0
        
        return {
            "steering_attempts": total_attempts,
            "successful_transitions": total_successful,
            "failed_transitions": max(0, total_attempts - total_successful),
            "avg_transition_time": round(avg_time, 3),
            "max_transition_time": round(max(successful_transition_times) if successful_transition_times else 0, 3),
            "verdict": analysis.verdict
        }
    
    def _compare_wireshark_raw_vs_processed(
        self,
        wireshark_raw: Optional[Dict[str, Any]],
        steering_analysis: Dict[str, Any],
        analysis: BandSteeringAnalysis
    ) -> Dict[str, Any]:
        """
        Compares Wireshark raw data with processed data to detect inconsistencies.
        Returns a dictionary with found mismatches.
        """
        if not wireshark_raw:
            return {
                "enabled": False,
                "reason": "wireshark_raw not available",
                "mismatches": []
            }
        
        mismatches = []
        raw_summary = wireshark_raw.get("summary", {})
        raw_btm = raw_summary.get("btm", {})
        raw_assoc = raw_summary.get("assoc", {})
        raw_reassoc = raw_summary.get("reassoc", {})
        
        # Comparison 1: BTM Requests
        raw_btm_requests = raw_btm.get("requests", 0)
        processed_steering_attempts = steering_analysis.get("steering_attempts", 0)
        if raw_btm_requests > 0 and processed_steering_attempts != raw_btm_requests:
            mismatches.append({
                "field": "btm_requests_vs_steering_attempts",
                "raw_value": raw_btm_requests,
                "processed_value": processed_steering_attempts,
                "delta": processed_steering_attempts - raw_btm_requests,
                "severity": "warning",
                "explanation": f"Steering attempts ({processed_steering_attempts}) may include Deauth/Disassoc in addition to BTM Requests ({raw_btm_requests})"
            })
        
        # Comparison 2: BTM Responses Accept vs Successful Transitions
        raw_btm_accept = raw_btm.get("responses_accept", 0)
        processed_successful = steering_analysis.get("successful_transitions", 0)
        # Use the max between successful transitions and BTM accepts (as in compliance checks)
        analysis_successful = max(
            sum(1 for t in analysis.transitions if t.is_successful),
            raw_btm_accept
        )
        if raw_btm_accept > 0 and processed_successful != analysis_successful:
            mismatches.append({
                "field": "btm_accept_vs_successful_transitions",
                "raw_value": raw_btm_accept,
                "processed_value": processed_successful,
                "expected_value": analysis_successful,
                "delta": processed_successful - analysis_successful,
                "severity": "error" if abs(processed_successful - analysis_successful) > 1 else "warning",
                "explanation": f"BTM Accept raw: {raw_btm_accept}, Successful transitions: {sum(1 for t in analysis.transitions if t.is_successful)}, Expected: {analysis_successful}, Processed: {processed_successful}"
            })
        
        # Comparison 3: Association/Reassociation counts (basic coherence)
        raw_assoc_req = raw_assoc.get("requests", 0)
        raw_assoc_resp = raw_assoc.get("responses", 0)
        raw_reassoc_req = raw_reassoc.get("requests", 0)
        raw_reassoc_resp = raw_reassoc.get("responses", 0)
        
        # Comparison 4: Total Deauth / Disassoc
        raw_deauth = raw_summary.get("deauth", {})
        raw_disassoc = raw_summary.get("disassoc", {})
        raw_deauth_count = raw_deauth.get("count", 0)
        raw_disassoc_count = raw_disassoc.get("count", 0)

        # Count steering events that are Deauth/Disassoc directed to the client
        processed_deauth = 0
        processed_disassoc = 0
        if analysis.transitions:
            for t in analysis.transitions:
                # Transitions do not contain all events 1:1, so here 
                # we only check if there is a gross deviation (e.g. 0 vs many).
                # Fine counting is done in compliance checks.
                pass
        # If Wireshark detects disconnections but the analysis doesn't see any
        if (raw_deauth_count + raw_disassoc_count) > 0 and analysis.loops_detected is False:
            mismatches.append({
                "field": "forced_disconnect_visibility",
                "raw_value": {
                    "deauth": raw_deauth_count,
                    "disassoc": raw_disassoc_count,
                },
                "processed_value": "no_loops_detected",
                "severity": "warning",
                "explanation": "Wireshark detects disconnections (Deauth/Disassoc) but the analysis does not mark loops; check stability in narrative report."
            })

        # Check inconsistencies in freq_band_map
        freq_band_inconsistencies = []
        freq_band_map = raw_summary.get("freq_band_map", {})
        for freq_str, band in freq_band_map.items():
            try:
                freq_val = int(freq_str)
                expected_band = "2.4GHz" if 2400 <= freq_val <= 2500 else ("5GHz" if 5000 <= freq_val <= 6000 else None)
                if expected_band and band != expected_band:
                    freq_band_inconsistencies.append({
                        "frequency": freq_val,
                        "raw_band": band,
                        "expected_band": expected_band
                    })
            except (ValueError, TypeError):
                pass
        
        if freq_band_inconsistencies:
            mismatches.append({
                "field": "freq_band_inconsistencies",
                "raw_value": freq_band_inconsistencies,
                "processed_value": None,
                "severity": "error",
                "explanation": f"{len(freq_band_inconsistencies)} inconsistencies detected between frequency and assigned band"
            })
        
        # Comparison 4: BTM Status Codes
        raw_status_codes = raw_btm.get("status_codes", [])
        processed_status_codes = []
        for event in analysis.btm_events:
            if event.status_code is not None and str(event.status_code) not in processed_status_codes:
                processed_status_codes.append(str(event.status_code))
        
        if set(raw_status_codes) != set(processed_status_codes):
            mismatches.append({
                "field": "btm_status_codes",
                "raw_value": raw_status_codes,
                "processed_value": processed_status_codes,
                "severity": "warning",
                "explanation": "Status codes may differ if events were filtered for the primary client"
            })
        
        return {
            "enabled": True,
            "total_mismatches": len(mismatches),
            "mismatches": mismatches,
            "summary": {
                "raw_btm_requests": raw_btm_requests,
                "raw_btm_responses": raw_btm.get("responses", 0),
                "raw_btm_accept": raw_btm_accept,
                "processed_steering_attempts": processed_steering_attempts,
                "processed_successful_transitions": processed_successful,
                "raw_assoc": f"{raw_assoc_req}/{raw_assoc_resp}",
                "raw_reassoc": f"{raw_reassoc_req}/{raw_reassoc_resp}"
            }
        }
    
    def _index_analysis_for_rag(self, analysis: BandSteeringAnalysis):
        """
        Converts the analysis result to text and indexes it in Qdrant.
        This allows the user to ask about results in the chat.
        """
        try:
            repo = get_qdrant_repository()
            
            # Create a textual summary of the analysis
            summary = (
                f"Band Steering Analysis Result for file {analysis.filename}. "
                f"Device: {analysis.devices[0].vendor} {analysis.devices[0].device_model if analysis.devices[0].device_model else ''}. "
                f"Final Verdict: {analysis.verdict}. "
                f"BTM Events: {analysis.btm_requests} requests, {analysis.btm_responses} responses. "
                f"BTM success rate: {analysis.btm_success_rate * 100}%. "
                f"Successful transitions: {analysis.successful_transitions}. "
                f"KVR Support: K={analysis.kvr_support.k_support}, V={analysis.kvr_support.v_support}, R={analysis.kvr_support.r_support}. "
            )
            
            # Add details of compliance checks
            for check in analysis.compliance_checks:
                status = "PASSED" if check.passed else "FAILED"
                summary += f"Check '{check.check_name}': {status}. {check.details}. "

            # In a real environment, it would use embedding_for_text from repo
            from ..utils.embeddings import embedding_for_text
            vector = embedding_for_text(summary)
            
            point = {
                "id": str(analysis.analysis_id),
                "vector": vector,
                "payload": {
                    "text": summary,
                    "source": analysis.filename,
                    "type": "analysis_result",
                    "timestamp": datetime.now().isoformat(),
                    "analysis_id": analysis.analysis_id
                }
            }
            
            repo.upsert_points([point])
            
        except Exception as e:
            pass

    def _save_analysis_result(self, analysis: BandSteeringAnalysis, device: DeviceInfo, original_file_path: Optional[str] = None) -> str:
        """
        Organizes files into folders by Brand/Model.
        Structure: data/analyses/{Vendor}/{Model_or_MAC}/{analysis_id}.json
        Also saves the original pcap file for later download.

        Persistence logic is kept here so as not to overload
        domain components (analysis, classification, etc.).
        """
        vendor_name = device.vendor.replace(" ", "_")
        device_id = device.device_model.replace(" ", "_") if device.device_model else device.mac_address.replace(":", "")
        
        target_dir = self.base_dir / vendor_name / device_id
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Save analysis JSON
        json_path = target_dir / f"{analysis.analysis_id}.json"
        
        # Save the original pcap file if it exists
        saved_pcap_path = None
        if original_file_path:
            # Ensure path is absolute
            original_path = Path(original_file_path)
            if not original_path.is_absolute():
                original_path = original_path.resolve()
            if original_path.exists():
                try:
                    # Copy the pcap file to the analysis folder
                    pcap_filename = original_path.name
                    # Clean UUID from name if it exists (format UUID_Name.pcap)
                    if "_" in pcap_filename and len(pcap_filename.split("_")[0]) == 36:
                        pcap_filename = "_".join(pcap_filename.split("_")[1:])
                    
                    saved_pcap_path = target_dir / f"{analysis.analysis_id}_{pcap_filename}"
                    shutil.copy2(original_path, saved_pcap_path)
                    saved_pcap_path = str(saved_pcap_path)
                except Exception:
                    saved_pcap_path = None
        
        # Save file path in analysis
        # NOTE: Do not assign directly to Pydantic object (it's not a model field)
        # It will be saved in the dict when serializing for JSON persistence
        
        with open(json_path, "w", encoding="utf-8") as f:
            # Convert to dict to add additional fields
            # Use model_dump with mode='json' to serialize datetime correctly
            analysis_dict = analysis.model_dump(mode='json', exclude_none=False)
            
            # Ensure raw_stats (which contains user_metadata) is ALWAYS saved
            # Although raw_stats is a model field, we force it explicitly
            # because model_dump may not include it if it's None or if there are serialization issues
            if hasattr(analysis, 'raw_stats'):
                analysis_dict["raw_stats"] = analysis.raw_stats
            # If attribute doesn't exist, simply don't include in JSON
            
            if saved_pcap_path:
                analysis_dict["original_file_path"] = saved_pcap_path
            
            # Ensure verdict is present in final dict
            if not analysis_dict.get("verdict") and getattr(analysis, "verdict", None):
                analysis_dict["verdict"] = analysis.verdict
            
            json.dump(analysis_dict, f, indent=4, ensure_ascii=False)
            
        return str(json_path)

    def _persist_analysis(
        self,
        analysis: BandSteeringAnalysis,
        device: DeviceInfo,
        file_path: Optional[str],
    ) -> str:
        """
        Orchestrates analysis persistence ensuring the original file path
        is resolved absolutely before delegating to `_save_analysis_result`.
        """
        original_file_path_abs = Path(file_path).resolve() if file_path else None
        return self._save_analysis_result(
            analysis=analysis,
            device=device,
            original_file_path=str(original_file_path_abs) if original_file_path_abs else None,
        )

    def get_brand_statistics(self, brand: str) -> Dict[str, Any]:
        """
        Returns aggregated statistics for a specific brand.
        """
        brand_dir = self.base_dir / brand.replace(" ", "_")
        if not brand_dir.exists():
            return {"error": "Brand not found"}
            
        # Logic to loop through files and average compliance scores, etc.
        # (Future implementation as needed)
        return {"brand": brand, "status": "active"}
