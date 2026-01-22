"""
Sleep Manager Module - Advanced Sleep Quality Analysis

Tracks baby's sleep patterns using motion detection data with:
- Breathing interval detection (inter-breath intervals)
- Sleep phase detection (Deep Sleep vs REM/Light Sleep)
- Breathing rate calculation (breaths per minute)
- Variability analysis for sleep quality scoring
- Comprehensive sleep report for parents
"""

import time
import logging
import statistics
import json
import os
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
from collections import deque
import threading

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('sleep_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('SleepManager')


class SleepState(Enum):
    """Possible sleep states for the baby."""
    UNKNOWN = "unknown"
    NO_BREATHING = "no_breathing"   # No movement - ALERT
    DEEP_SLEEP = "deep_sleep"       # Quiet Sleep / Non-REM - regular breathing
    LIGHT_SLEEP = "light_sleep"     # Active Sleep / REM - irregular breathing
    SPASM = "spasm"                 # Temporary movement during sleep
    AWAKE = "awake"                 # Sustained active movement


class SleepEvent:
    """Represents a sleep-related event."""
    def __init__(self, event_type: str, timestamp: float, data: Optional[Dict] = None):
        self.event_type = event_type
        self.timestamp = timestamp
        self.data = data or {}


class BreathingAnalyzer:
    """
    Analyzes breathing patterns to detect inter-breath intervals
    and calculate breathing rate and variability.
    """
    
    # Thresholds for breath detection
    BREATH_PEAK_THRESHOLD = 50000     # Minimum motion to count as a breath
    MIN_BREATH_INTERVAL = 1.0         # Minimum seconds between breaths (60 BPM max)
    MAX_BREATH_INTERVAL = 5.0         # Maximum seconds between breaths (12 BPM min)
    
    # Variability thresholds for sleep phase detection
    LOW_VARIABILITY_THRESHOLD = 0.15   # < 15% = Deep Sleep
    HIGH_VARIABILITY_THRESHOLD = 0.30  # > 30$ = Light/REM Sleep
    
    def __init__(self):
        self.breath_timestamps: deque = deque(maxlen=100)  # Last 100 detected breaths
        self.breath_intervals: deque = deque(maxlen=50)    # Last 50 intervals
        self.last_peak_time: Optional[float] = None
        self.in_peak: bool = False
        
    def reset(self):
        """Reset the analyzer."""
        self.breath_timestamps.clear()
        self.breath_intervals.clear()
        self.last_peak_time = None
        self.in_peak = False
    
    def process_motion(self, motion_score: float, timestamp: float) -> Optional[float]:
        """
        Process a motion score and detect breath peaks.
        Returns the interval since last breath if a new breath is detected.
        """
        if motion_score > self.BREATH_PEAK_THRESHOLD:
            if not self.in_peak:
                # New breath detected
                self.in_peak = True
                
                if self.last_peak_time is not None:
                    interval = timestamp - self.last_peak_time
                    
                    # Always update last_peak_time to prevent stale timestamps
                    self.last_peak_time = timestamp
                    
                    # Validate interval is reasonable
                    if self.MIN_BREATH_INTERVAL <= interval <= self.MAX_BREATH_INTERVAL:
                        self.breath_timestamps.append(timestamp)
                        self.breath_intervals.append(interval)
                        return interval
                    # If interval is too long, treat as first breath of new sequence
                    elif interval > self.MAX_BREATH_INTERVAL:
                        self.breath_timestamps.append(timestamp)
                else:
                    # First breath
                    self.last_peak_time = timestamp
                    self.breath_timestamps.append(timestamp)
        else:
            self.in_peak = False
        
        return None
    
    def get_breathing_rate(self) -> float:
        """
        Calculate current breathing rate in breaths per minute.
        Returns 0 if not enough data.
        """
        if len(self.breath_intervals) < 3:
            return 0.0
        
        # Use recent intervals
        recent = list(self.breath_intervals)[-10:]
        avg_interval = statistics.mean(recent)
        
        if avg_interval > 0:
            return 60.0 / avg_interval
        return 0.0
    
    def get_breathing_variability(self) -> float:
        """
        Calculate the coefficient of variation (CV) of breathing intervals.
        CV = std / mean - gives a normalized measure of variability.
        Returns 0 if not enough data.
        """
        if len(self.breath_intervals) < 5:
            return 0.0
        
        recent = list(self.breath_intervals)[-20:]
        mean_interval = statistics.mean(recent)
        
        if mean_interval > 0 and len(recent) >= 2:
            std_interval = statistics.stdev(recent)
            return std_interval / mean_interval
        return 0.0
    
    def get_sleep_phase(self) -> str:
        """
        Determine sleep phase based on breathing variability.
        Returns: 'deep', 'light', or 'unknown'
        """
        variability = self.get_breathing_variability()
        
        if variability == 0:
            return 'unknown'
        elif variability < self.LOW_VARIABILITY_THRESHOLD:
            return 'deep'  # Quiet Sleep - regular breathing
        elif variability > self.HIGH_VARIABILITY_THRESHOLD:
            return 'light'  # Active/REM Sleep - irregular breathing
        else:
            return 'transitional'  # Between phases
    
    def get_stats(self) -> Dict[str, Any]:
        """Get breathing statistics."""
        return {
            'breathing_rate_bpm': round(self.get_breathing_rate(), 1),
            'breathing_variability': round(self.get_breathing_variability(), 3),
            'sleep_phase': self.get_sleep_phase(),
            'breath_count': len(self.breath_timestamps),
            'intervals_recorded': len(self.breath_intervals),
        }


class SleepManager:
    """
    Advanced sleep state detection and quality analysis.
    
    Features:
    - Sliding window motion analysis
    - Breathing pattern detection
    - Sleep phase detection (Deep vs Light/REM)
    - Comprehensive sleep quality metrics
    - Detailed parent-friendly reports
    """
    
    # Motion thresholds (calibrated for actual camera readings)
    NO_MOTION_THRESHOLD = 10000         # Mean must be below this to trigger no_breathing
    BREATHING_LOW = 10000               # Minimum mean for breathing detection  
    BREATHING_HIGH = 1500000            # Maximum mean for sleep movement
    MOVEMENT_THRESHOLD = 5000000        # Mean above this = active movement
    AWAKE_THRESHOLD = 10000000          # High sustained movement (very active)
    
    # Timing constants
    BUFFER_DURATION = 60.0              # Keep 60 seconds of history
    ANALYSIS_WINDOW = 10.0              # Analyze last 10 seconds
    SPASM_WINDOW = 5.0                  # Spasm detection window
    
    # Hysteresis - confirmation times
    CONFIRM_AWAKE_SECONDS = 8.0         # Sustained movement to confirm awake
    CONFIRM_SLEEP_SECONDS = 15.0        # Calm period to confirm sleep
    CONFIRM_NO_BREATHING_SECONDS = 12.0 # Silence to trigger alert
    CONFIRM_PHASE_CHANGE_SECONDS = 30.0 # Time to confirm sleep phase change
    
    # History file path
    HISTORY_FILE = "sleep_history.json"
    
    # Valid state transitions
    VALID_TRANSITIONS = {
        SleepState.UNKNOWN: [SleepState.NO_BREATHING, SleepState.DEEP_SLEEP, 
                             SleepState.LIGHT_SLEEP, SleepState.AWAKE],
        SleepState.NO_BREATHING: [SleepState.DEEP_SLEEP, SleepState.LIGHT_SLEEP, 
                                   SleepState.AWAKE],
        SleepState.DEEP_SLEEP: [SleepState.LIGHT_SLEEP, SleepState.SPASM, 
                                 SleepState.NO_BREATHING, SleepState.AWAKE],
        SleepState.LIGHT_SLEEP: [SleepState.DEEP_SLEEP, SleepState.SPASM, 
                                  SleepState.NO_BREATHING, SleepState.AWAKE],
        SleepState.SPASM: [SleepState.DEEP_SLEEP, SleepState.LIGHT_SLEEP, 
                           SleepState.AWAKE],
        SleepState.AWAKE: [SleepState.DEEP_SLEEP, SleepState.LIGHT_SLEEP],
    }
    
    def __init__(self):
        """Initialize the sleep manager."""
        # Use RLock (re-entrant lock) to allow nested calls like get_sleep_report() -> get_stats()
        self.lock = threading.RLock()
        self.breathing_analyzer = BreathingAnalyzer()
        self.session_id: Optional[str] = None
        self._reset_session()
        
    def _reset_session(self):
        """Reset all session data."""
        self.session_id = str(uuid.uuid4())
        self.session_start_time: Optional[float] = None
        self.current_state = SleepState.UNKNOWN
        
        # Motion history buffer: (timestamp, score)
        self.motion_buffer: deque = deque()
        
        # State tracking
        self.state_start_time: float = 0
        self.pending_state: Optional[SleepState] = None
        self.pending_state_time: Optional[float] = None
        
        # Spasm tracking
        self.spasm_start_time: Optional[float] = None
        self.pre_spasm_state: Optional[SleepState] = None
        
        # Sleep phase tracking
        self.current_phase: str = 'unknown'
        self.phase_start_time: float = 0
        
        # Comprehensive Metrics
        self.total_sleep_seconds: float = 0
        self.deep_sleep_seconds: float = 0
        self.light_sleep_seconds: float = 0
        self.last_sleep_start: Optional[float] = None
        self.wake_up_count: int = 0
        self.spasm_count: int = 0
        self.micro_arousals: int = 0  # Brief movements without full wake
        
        # Breathing metrics (reset analyzer)
        self.breathing_analyzer.reset()
        
        # Sleep cycles
        self.sleep_cycles: List[Dict] = []  # Track complete sleep cycles
        self.current_cycle_start: Optional[float] = None
        
        # Events history
        self.events: List[SleepEvent] = []
        
        # Cache for stats
        self._last_update_time: float = 0
        self._last_log_time: float = 0
    
    def start_session(self):
        """Start a new monitoring session."""
        with self.lock:
            self._reset_session()
            self.session_start_time = time.time()
            logger.info("Session started")
    
    def stop_session(self):
        """Stop the current monitoring session and save to history."""
        with self.lock:
            if self.last_sleep_start is not None:
                self.total_sleep_seconds += time.time() - self.last_sleep_start
                self.last_sleep_start = None
            
            # Save to history if session had meaningful data
            if self.session_start_time is not None and self.total_sleep_seconds >= 60:
                self._save_to_history()
            
            logger.info(f"Session stopped. Total sleep: {self.total_sleep_seconds:.1f}s")
    
    def update(self, motion_score: float) -> SleepState:
        """
        Update sleep state based on current motion score.
        """
        with self.lock:
            current_time = time.time()
            
            # Auto-start session if not started
            if self.session_start_time is None:
                self.session_start_time = current_time
            
            # Add to buffer
            self.motion_buffer.append((current_time, float(motion_score)))

            # Log current motion score
            logger.debug(f"Motion Score: {motion_score}")
            
            # Process breathing
            breath_interval = self.breathing_analyzer.process_motion(motion_score, current_time)
            if breath_interval:
                logger.debug(f"Breath detected: interval={breath_interval:.2f}s, rate={self.breathing_analyzer.get_breathing_rate():.1f} BPM")
            
            # Clean old entries from buffer
            self._clean_buffer(current_time)
            
            # Analyze the buffer and determine state
            analysis = self._analyze_buffer(current_time)
            
            # Determine target state based on analysis
            target_state = self._determine_state(analysis, current_time)
            
            # Handle state transition with hysteresis
            self._handle_transition(target_state, current_time, analysis)
            
            # Update metrics
            self._update_metrics(current_time, analysis)
            
            self._last_update_time = current_time
            return self.current_state
    
    def _clean_buffer(self, current_time: float):
        """Remove entries older than BUFFER_DURATION."""
        cutoff = current_time - self.BUFFER_DURATION
        while self.motion_buffer and self.motion_buffer[0][0] < cutoff:
            self.motion_buffer.popleft()
    
    def _analyze_buffer(self, current_time: float) -> Dict[str, Any]:
        """Analyze the motion buffer and return statistics."""
        # Get scores within analysis window
        window_start = current_time - self.ANALYSIS_WINDOW
        window_scores = [s for t, s in self.motion_buffer if t >= window_start]
        
        # Get scores for spasm detection (shorter window)
        spasm_start = current_time - self.SPASM_WINDOW
        spasm_scores = [s for t, s in self.motion_buffer if t >= spasm_start]
        
        # Calculate statistics
        if len(window_scores) >= 2:
            mean_score = statistics.mean(window_scores)
            std_score = statistics.stdev(window_scores)
            max_score = max(window_scores)
            min_score = min(window_scores)
        elif len(window_scores) == 1:
            mean_score = window_scores[0]
            std_score = 0
            max_score = min_score = window_scores[0]
        else:
            mean_score = std_score = max_score = min_score = 0
        
        # Calculate spasm window stats
        spasm_max = max(spasm_scores) if spasm_scores else 0
        
        # Breathing analysis
        breathing_stats = self.breathing_analyzer.get_stats()
        
        # Detect sustained high movement
        high_movement_ratio = sum(1 for s in window_scores if s > self.MOVEMENT_THRESHOLD) / max(len(window_scores), 1)
        
        # Detect no motion - use MEAN
        is_no_motion = mean_score < self.NO_MOTION_THRESHOLD
        
        return {
            'mean': mean_score,
            'std': std_score,
            'max': max_score,
            'min': min_score,
            'high_movement_ratio': high_movement_ratio,
            'is_no_motion': is_no_motion,
            'sample_count': len(window_scores),
            'spasm_max': spasm_max,
            'current_score': self.motion_buffer[-1][1] if self.motion_buffer else 0,
            'breathing': breathing_stats,
        }
    
    def _determine_state(self, analysis: Dict, current_time: float) -> SleepState:
        """Determine target state based on buffer analysis."""
        mean = analysis['mean']
        high_ratio = analysis['high_movement_ratio']
        is_no_motion = analysis['is_no_motion']
        spasm_max = analysis['spasm_max']
        breathing = analysis['breathing']
        
        # Priority 1: No breathing detection
        if is_no_motion:
            return SleepState.NO_BREATHING
        
        # Priority 2: Check for sustained high movement (awake)
        if high_ratio > 0.5 and mean > self.MOVEMENT_THRESHOLD:
            return SleepState.AWAKE
        
        # Priority 3: Spasm detection - sudden spike during sleep
        if self.current_state in (SleepState.DEEP_SLEEP, SleepState.LIGHT_SLEEP, SleepState.SPASM):
            if spasm_max > self.AWAKE_THRESHOLD and high_ratio < 0.3:
                return SleepState.SPASM
        
        # Priority 4: Determine sleep phase based on breathing variability
        if mean < self.AWAKE_THRESHOLD:
            sleep_phase = breathing.get('sleep_phase', 'unknown')
            
            if sleep_phase == 'deep':
                return SleepState.DEEP_SLEEP
            elif sleep_phase in ('light', 'transitional'):
                return SleepState.LIGHT_SLEEP
            else:
                # Default to light sleep if we can't determine phase
                # More conservative - assumes baby is in lighter sleep
                return SleepState.LIGHT_SLEEP if self.current_state == SleepState.UNKNOWN else self.current_state
        
        # Default
        return self.current_state if self.current_state != SleepState.UNKNOWN else SleepState.LIGHT_SLEEP
    
    def _handle_transition(self, target_state: SleepState, 
                           current_time: float, analysis: Dict):
        """Handle state transitions with hysteresis."""
        # Check if transition is valid
        if target_state not in self.VALID_TRANSITIONS.get(self.current_state, []):
            if target_state != self.current_state:
                target_state = self._find_valid_transition(target_state)
        
        # Same state - handle pending
        if target_state == self.current_state:
            if self.current_state == SleepState.SPASM:
                if current_time - self.spasm_start_time > self.SPASM_WINDOW:
                    self._execute_transition(self.pre_spasm_state or SleepState.LIGHT_SLEEP, 
                                            current_time, "spasm_ended")
            if self.pending_state is None:
                return
            self.pending_state = None
            self.pending_state_time = None
            return
        
        # Get required confirmation time
        confirm_time = self._get_confirmation_time(self.current_state, target_state)
        
        # Start or continue pending transition
        if self.pending_state == target_state:
            if current_time - self.pending_state_time >= confirm_time:
                self._execute_transition(target_state, current_time, "confirmed")
        else:
            self.pending_state = target_state
            self.pending_state_time = current_time
            logger.debug(f"Pending transition: {self.current_state.value} -> {target_state.value} "
                        f"(need {confirm_time:.1f}s confirmation)")
    
    def _find_valid_transition(self, target_state: SleepState) -> SleepState:
        """Find a valid intermediate state for transition."""
        if self.current_state == SleepState.AWAKE:
            return SleepState.LIGHT_SLEEP
        if self.current_state == SleepState.NO_BREATHING:
            return target_state
        return self.current_state
    
    def _get_confirmation_time(self, from_state: SleepState, to_state: SleepState) -> float:
        """Get the required confirmation time for a state transition."""
        if to_state == SleepState.SPASM:
            return 0.5
        if to_state == SleepState.NO_BREATHING:
            return self.CONFIRM_NO_BREATHING_SECONDS
        if to_state == SleepState.AWAKE:
            return self.CONFIRM_AWAKE_SECONDS
        
        # Sleep phase transitions
        if from_state == SleepState.DEEP_SLEEP and to_state == SleepState.LIGHT_SLEEP:
            return self.CONFIRM_PHASE_CHANGE_SECONDS
        if from_state == SleepState.LIGHT_SLEEP and to_state == SleepState.DEEP_SLEEP:
            return self.CONFIRM_PHASE_CHANGE_SECONDS
        
        if from_state == SleepState.AWAKE:
            return self.CONFIRM_SLEEP_SECONDS
        
        return 3.0
    
    def _execute_transition(self, new_state: SleepState, current_time: float, reason: str):
        """Execute a state transition."""
        old_state = self.current_state
        
        # Track spasm
        if new_state == SleepState.SPASM:
            self.spasm_start_time = current_time
            self.pre_spasm_state = old_state
            self.spasm_count += 1
            self.events.append(SleepEvent("spasm", current_time))
        
        # Track wake up
        if old_state in (SleepState.DEEP_SLEEP, SleepState.LIGHT_SLEEP) and new_state == SleepState.AWAKE:
            self.wake_up_count += 1
            if self.last_sleep_start is not None:
                sleep_duration = current_time - self.last_sleep_start
                self.events.append(SleepEvent("wake_up", current_time, {"sleep_duration": sleep_duration}))
                self.last_sleep_start = None
                
                # Record completed sleep cycle
                if self.current_cycle_start is not None:
                    cycle_duration = current_time - self.current_cycle_start
                    self.sleep_cycles.append({
                        'start': self.current_cycle_start,
                        'end': current_time,
                        'duration_minutes': cycle_duration / 60
                    })
                    self.current_cycle_start = None
        
        # Track fell asleep
        if old_state in (SleepState.AWAKE, SleepState.UNKNOWN) and \
           new_state in (SleepState.DEEP_SLEEP, SleepState.LIGHT_SLEEP):
            self.events.append(SleepEvent("fell_asleep", current_time))
            self.last_sleep_start = current_time
            self.current_cycle_start = current_time
        
        # Track sleep phase change
        if old_state == SleepState.DEEP_SLEEP and new_state == SleepState.LIGHT_SLEEP:
            self.events.append(SleepEvent("phase_change", current_time, {"from": "deep", "to": "light"}))
        elif old_state == SleepState.LIGHT_SLEEP and new_state == SleepState.DEEP_SLEEP:
            self.events.append(SleepEvent("phase_change", current_time, {"from": "light", "to": "deep"}))
        
        # Track no breathing alert
        if new_state == SleepState.NO_BREATHING:
            self.events.append(SleepEvent("no_breathing_alert", current_time))
        
        # Execute transition
        self.current_state = new_state
        self.state_start_time = current_time
        self.pending_state = None
        self.pending_state_time = None
        
        logger.info(f"State transition: {old_state.value} -> {new_state.value} ({reason})")
    
    def _update_metrics(self, current_time: float, analysis: Dict):
        """Update tracking metrics."""
        if self._last_update_time > 0:
            delta = current_time - self._last_update_time
            
            # Update sleep phase times
            if self.current_state == SleepState.DEEP_SLEEP:
                self.deep_sleep_seconds += delta
                self.total_sleep_seconds += delta
            elif self.current_state == SleepState.LIGHT_SLEEP:
                self.light_sleep_seconds += delta
                self.total_sleep_seconds += delta
            elif self.current_state == SleepState.SPASM:
                # Spasms count as sleep (they happen during sleep)
                self.light_sleep_seconds += delta
                self.total_sleep_seconds += delta
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current sleep statistics."""
        with self.lock:
            current_time = time.time()
            
            # Calculate session duration
            session_duration = 0
            if self.session_start_time is not None:
                session_duration = current_time - self.session_start_time
            
            # Current analysis
            analysis = self._analyze_buffer(current_time) if self.motion_buffer else {}
            breathing = analysis.get('breathing', {})
            
            # Sleep quality score (0-100)
            sleep_quality = self._calculate_sleep_quality(session_duration)
            
            # Time in current state
            state_duration = current_time - self.state_start_time if self.state_start_time > 0 else 0
            
            # Breathing detected now
            breathing_now = self.current_state in (SleepState.DEEP_SLEEP, SleepState.LIGHT_SLEEP)
            
            return {
                # Current State
                "current_state": self.current_state.value,
                "breathing_detected": breathing_now,
                "state_duration_seconds": int(state_duration),
                
                # Session Summary
                "session_duration_minutes": int(session_duration / 60),
                "session_duration_seconds": int(session_duration),
                
                # Sleep Duration Breakdown
                "total_sleep_minutes": int(self.total_sleep_seconds / 60),
                "total_sleep_seconds": int(self.total_sleep_seconds),
                "deep_sleep_minutes": int(self.deep_sleep_seconds / 60),
                "deep_sleep_seconds": int(self.deep_sleep_seconds),
                "light_sleep_minutes": int(self.light_sleep_seconds / 60),
                "light_sleep_seconds": int(self.light_sleep_seconds),
                
                # Sleep Quality
                "sleep_quality_score": sleep_quality,
                "deep_sleep_percent": int((self.deep_sleep_seconds / max(self.total_sleep_seconds, 1)) * 100),
                "light_sleep_percent": int((self.light_sleep_seconds / max(self.total_sleep_seconds, 1)) * 100),
                
                # Events
                "wake_ups": self.wake_up_count,
                "spasms": self.spasm_count,
                "sleep_cycles_completed": len(self.sleep_cycles),
                
                # Breathing Analysis
                "breathing_rate_bpm": breathing.get('breathing_rate_bpm', 0),
                "breathing_variability": breathing.get('breathing_variability', 0),
                "breathing_phase": breathing.get('sleep_phase', 'unknown'),
                "breaths_detected": breathing.get('breath_count', 0),
                
                # Motion Analysis
                "last_motion_score": float(analysis.get('current_score', 0)),
                "motion_mean": float(analysis.get('mean', 0)),
                "motion_std": float(analysis.get('std', 0)),
                
                # Misc
                "events_count": len(self.events),
                "pending_transition": self.pending_state.value if self.pending_state else None,
            }
    
    def _calculate_sleep_quality(self, session_duration: float) -> int:
        """
        Calculate a sleep quality score (0-100) based on multiple factors:
        - Deep sleep ratio (higher = better)
        - Wake-ups (fewer = better)
        - Breathing regularity (more regular = better during deep sleep)
        """
        if session_duration < 60 or self.total_sleep_seconds < 60:
            return 0  # Not enough data
        
        score = 100
        
        # Factor 1: Deep sleep ratio (target: 40-50% for babies)
        deep_ratio = self.deep_sleep_seconds / max(self.total_sleep_seconds, 1)
        if deep_ratio < 0.2:
            score -= 20  # Too little deep sleep
        elif deep_ratio < 0.35:
            score -= 10
        # Optimal is 0.35-0.50, no penalty
        elif deep_ratio > 0.6:
            score -= 5  # Too much deep sleep is unusual
        
        # Factor 2: Wake-ups (penalize fragmented sleep)
        # Expected: ~1 wake-up per hour is normal
        expected_wakes = session_duration / 3600
        excess_wakes = max(0, self.wake_up_count - expected_wakes)
        score -= min(30, int(excess_wakes * 10))  # -10 per extra wake-up, max -30
        
        # Factor 3: Spasms (normal but too many indicates restless sleep)
        if self.spasm_count > 10:
            score -= min(10, (self.spasm_count - 10))  # Penalize excessive spasms
        
        # Factor 4: Breathing regularity (during detected intervals)
        breathing_stats = self.breathing_analyzer.get_stats()
        variability = breathing_stats.get('breathing_variability', 0)
        
        # Very high variability might indicate restless sleep
        if variability > 0.4:
            score -= 10
        
        return max(0, min(100, score))
    
    def get_sleep_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive sleep report for parents.
        """
        with self.lock:
            stats = self.get_stats()
            current_time = time.time()
            
            # Format durations
            total_mins = stats['total_sleep_minutes']
            deep_mins = stats['deep_sleep_minutes']
            light_mins = stats['light_sleep_minutes']
            
            # Sleep cycle info
            avg_cycle = 0
            if self.sleep_cycles:
                avg_cycle = sum(c['duration_minutes'] for c in self.sleep_cycles) / len(self.sleep_cycles)
            
            # Breathing rate interpretation
            bpm = stats['breathing_rate_bpm']
            breathing_status = "normal"
            if bpm > 0:
                if bpm < 25:
                    breathing_status = "slow"
                elif bpm > 60:
                    breathing_status = "fast"
            
            return {
                "report_generated_at": current_time,
                
                # Summary for parents
                "summary": {
                    "total_sleep": f"{total_mins // 60}h {total_mins % 60}m",
                    "quality_score": stats['sleep_quality_score'],
                    "quality_rating": self._get_quality_rating(stats['sleep_quality_score']),
                },
                
                # Detailed breakdown
                "sleep_breakdown": {
                    "deep_sleep": f"{deep_mins}m ({stats['deep_sleep_percent']}%)",
                    "light_sleep": f"{light_mins}m ({stats['light_sleep_percent']}%)",
                    "description": self._get_breakdown_description(stats['deep_sleep_percent']),
                },
                
                # Events
                "events_summary": {
                    "wake_ups": self.wake_up_count,
                    "spasms": self.spasm_count,
                    "sleep_cycles": len(self.sleep_cycles),
                    "average_cycle_minutes": round(avg_cycle, 1) if avg_cycle > 0 else None,
                },
                
                # Breathing
                "breathing": {
                    "average_rate_bpm": stats['breathing_rate_bpm'],
                    "status": breathing_status,
                    "variability": round(stats['breathing_variability'] * 100, 1),  # As percentage
                    "current_phase": stats['breathing_phase'],
                },
                
                # Raw stats for app
                "raw_stats": stats,
            }
    
    def _get_quality_rating(self, score: int) -> str:
        """Convert score to human-readable rating."""
        if score >= 85:
            return "Excellent"
        elif score >= 70:
            return "Good"
        elif score >= 50:
            return "Fair"
        elif score >= 30:
            return "Poor"
        else:
            return "Very Poor"
    
    def _get_breakdown_description(self, deep_percent: int) -> str:
        """Get a description of the sleep breakdown."""
        if deep_percent >= 40:
            return "Good balance of deep and light sleep. Deep sleep promotes physical growth."
        elif deep_percent >= 25:
            return "Normal sleep pattern. Baby is cycling between sleep phases."
        elif deep_percent >= 10:
            return "Mostly light/REM sleep. Important for brain development."
        else:
            return "Very little deep sleep detected. Baby may be in active sleep phase."
    
    def get_recent_events(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get the most recent sleep events."""
        with self.lock:
            recent = self.events[-count:] if len(self.events) > count else self.events
            return [
                {
                    "type": e.event_type,
                    "timestamp": e.timestamp,
                    "data": e.data
                }
                for e in recent
            ]
    
    def _save_to_history(self):
        """Save the current session report to the history file."""
        try:
            report = self.get_sleep_report()
            
            # Create history entry with session metadata
            history_entry = {
                "id": self.session_id,
                "timestamp": self.session_start_time,
                "date_iso": datetime.fromtimestamp(self.session_start_time).isoformat(),
                "duration_seconds": int(self.total_sleep_seconds),
                "duration_formatted": report['summary']['total_sleep'],
                "quality_score": report['summary']['quality_score'],
                "quality_rating": report['summary']['quality_rating'],
                "report": report
            }
            
            # Load existing history
            history = self._load_history()
            
            # Add new entry
            history.append(history_entry)
            
            # Keep only last 100 entries
            if len(history) > 100:
                history = history[-100:]
            
            # Save back to file
            with open(self.HISTORY_FILE, 'w') as f:
                json.dump(history, f, indent=2)
            
            logger.info(f"Session {self.session_id} saved to history")
            
        except Exception as e:
            logger.error(f"Error saving to history: {e}")
    
    def _load_history(self) -> List[Dict]:
        """Load history from file."""
        if not os.path.exists(self.HISTORY_FILE):
            return []
        
        try:
            with open(self.HISTORY_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading history: {e}")
            return []
    
    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get list of past sleep sessions (summary only).
        Returns most recent sessions first.
        """
        with self.lock:
            history = self._load_history()
            
            # Return most recent first, with summary data only
            summaries = []
            for entry in reversed(history[-limit:]):
                summaries.append({
                    "id": entry.get("id"),
                    "timestamp": entry.get("timestamp"),
                    "date_iso": entry.get("date_iso"),
                    "duration_seconds": entry.get("duration_seconds"),
                    "duration_formatted": entry.get("duration_formatted"),
                    "quality_score": entry.get("quality_score"),
                    "quality_rating": entry.get("quality_rating"),
                })
            
            return summaries
    
    def get_session_report(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the full report for a specific session by ID.
        Returns None if session not found.
        """
        with self.lock:
            history = self._load_history()
            
            for entry in history:
                if entry.get("id") == session_id:
                    return entry.get("report")
            
            return None
    
    def set_thresholds(self, **kwargs):
        """Update detection thresholds."""
        with self.lock:
            for key, value in kwargs.items():
                if hasattr(self, key.upper()) and value is not None:
                    setattr(self, key.upper(), value)
                    logger.info(f"Threshold updated: {key}={value}")


# Global singleton instance
_sleep_manager: Optional[SleepManager] = None
_sleep_manager_lock = threading.Lock()


def get_sleep_manager() -> SleepManager:
    """Get or create the global SleepManager instance."""
    global _sleep_manager
    with _sleep_manager_lock:
        if _sleep_manager is None:
            _sleep_manager = SleepManager()
        return _sleep_manager
