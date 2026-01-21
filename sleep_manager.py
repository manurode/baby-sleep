"""
Sleep Manager Module - Advanced State Detection

Tracks baby's sleep patterns using motion detection data with:
- Sliding window analysis (not instant snapshots)
- Statistical analysis (mean, std dev, rhythm detection)
- Spasm vs Awake differentiation
- Hysteresis to prevent rapid state changes
- Valid state transition matrix
"""

import time
import logging
import statistics
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
    DEEP_SLEEP = "deep_sleep"       # Stable low movement (breathing rhythm)
    SLEEPING = "sleeping"           # Light sleep with some movement
    SPASM = "spasm"                 # Temporary movement during sleep
    AWAKE = "awake"                 # Sustained active movement


class SleepEvent:
    """Represents a sleep-related event."""
    def __init__(self, event_type: str, timestamp: float, data: Optional[Dict] = None):
        self.event_type = event_type
        self.timestamp = timestamp
        self.data = data or {}


class SleepManager:
    """
    Advanced sleep state detection using sliding window analysis.
    
    Key Concepts:
    - Maintains a 60-second buffer of motion scores
    - Analyzes patterns over 10-second windows
    - Uses hysteresis for state confirmation
    - Detects spasms vs sustained wakefulness
    """
    
    # Thresholds (calibrated for actual camera readings)
    NO_MOTION_THRESHOLD = 50000        # Below this = no breathing detected
    BREATHING_LOW = 100000             # Minimum for breathing detection
    BREATHING_HIGH = 1500000           # Maximum for sleep movement
    MOVEMENT_THRESHOLD = 2000000       # Above this = active movement
    AWAKE_THRESHOLD = 3000000          # High sustained movement
    
    # Timing constants
    BUFFER_DURATION = 60.0             # Keep 60 seconds of history
    ANALYSIS_WINDOW = 10.0             # Analyze last 10 seconds
    SPASM_WINDOW = 5.0                 # Spasm detection window
    
    # Hysteresis - confirmation times
    CONFIRM_AWAKE_SECONDS = 8.0        # Sustained movement to confirm awake
    CONFIRM_SLEEP_SECONDS = 15.0       # Calm period to confirm sleep
    CONFIRM_NO_BREATHING_SECONDS = 12.0 # Silence to trigger alert
    CONFIRM_DEEP_SLEEP_SECONDS = 10.0  # Stable breathing to confirm deep sleep
    
    # Valid state transitions
    VALID_TRANSITIONS = {
        SleepState.UNKNOWN: [SleepState.NO_BREATHING, SleepState.DEEP_SLEEP, 
                             SleepState.SLEEPING, SleepState.AWAKE],
        SleepState.NO_BREATHING: [SleepState.DEEP_SLEEP, SleepState.SLEEPING, 
                                   SleepState.AWAKE],
        SleepState.DEEP_SLEEP: [SleepState.SLEEPING, SleepState.SPASM, 
                                 SleepState.NO_BREATHING, SleepState.AWAKE],
        SleepState.SLEEPING: [SleepState.DEEP_SLEEP, SleepState.SPASM, 
                               SleepState.NO_BREATHING, SleepState.AWAKE],
        SleepState.SPASM: [SleepState.DEEP_SLEEP, SleepState.SLEEPING, 
                           SleepState.AWAKE],
        SleepState.AWAKE: [SleepState.SLEEPING, SleepState.DEEP_SLEEP],
    }
    
    def __init__(self):
        """Initialize the sleep manager."""
        self.lock = threading.Lock()
        self._reset_session()
        
    def _reset_session(self):
        """Reset all session data."""
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
        
        # Metrics
        self.total_sleep_seconds: float = 0
        self.last_sleep_start: Optional[float] = None
        self.wake_up_count: int = 0
        self.spasm_count: int = 0
        self.breathing_detected_seconds: float = 0
        
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
        """Stop the current monitoring session."""
        with self.lock:
            if self.last_sleep_start is not None:
                self.total_sleep_seconds += time.time() - self.last_sleep_start
                self.last_sleep_start = None
            logger.info(f"Session stopped. Total sleep: {self.total_sleep_seconds:.1f}s")
    
    def update(self, motion_score: float) -> SleepState:
        """
        Update sleep state based on current motion score.
        Uses sliding window analysis instead of instant snapshots.
        """
        with self.lock:
            current_time = time.time()
            
            # Auto-start session if not started
            if self.session_start_time is None:
                self.session_start_time = current_time
            
            # Add to buffer
            self.motion_buffer.append((current_time, float(motion_score)))
            
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
            
            # Debug logging every 5 seconds
            if current_time - self._last_log_time > 5:
                logger.debug(
                    f"Analysis: mean={analysis['mean']:.0f}, std={analysis['std']:.0f}, "
                    f"max={analysis['max']:.0f}, duration={analysis['window_duration']:.1f}s | "
                    f"State: {self.current_state.value}"
                )
                self._last_log_time = current_time
            
            self._last_update_time = current_time
            return self.current_state
    
    def _clean_buffer(self, current_time: float):
        """Remove entries older than BUFFER_DURATION."""
        cutoff = current_time - self.BUFFER_DURATION
        while self.motion_buffer and self.motion_buffer[0][0] < cutoff:
            self.motion_buffer.popleft()
    
    def _analyze_buffer(self, current_time: float) -> Dict[str, Any]:
        """
        Analyze the motion buffer and return statistics.
        """
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
        spasm_mean = statistics.mean(spasm_scores) if spasm_scores else 0
        
        # Detect breathing rhythm (low variance in breathing range)
        is_rhythmic = (
            self.BREATHING_LOW < mean_score < self.BREATHING_HIGH and
            std_score < mean_score * 0.5  # Low relative variance
        )
        
        # Detect sustained high movement
        high_movement_ratio = sum(1 for s in window_scores if s > self.MOVEMENT_THRESHOLD) / max(len(window_scores), 1)
        
        # Detect no motion
        no_motion_ratio = sum(1 for s in window_scores if s < self.NO_MOTION_THRESHOLD) / max(len(window_scores), 1)
        
        return {
            'mean': mean_score,
            'std': std_score,
            'max': max_score,
            'min': min_score,
            'is_rhythmic': is_rhythmic,
            'high_movement_ratio': high_movement_ratio,
            'no_motion_ratio': no_motion_ratio,
            'sample_count': len(window_scores),
            'window_duration': min(self.ANALYSIS_WINDOW, current_time - self.session_start_time),
            'spasm_max': spasm_max,
            'spasm_mean': spasm_mean,
            'current_score': self.motion_buffer[-1][1] if self.motion_buffer else 0,
        }
    
    def _determine_state(self, analysis: Dict, current_time: float) -> SleepState:
        """
        Determine target state based on buffer analysis.
        """
        mean = analysis['mean']
        max_score = analysis['max']
        high_ratio = analysis['high_movement_ratio']
        no_motion_ratio = analysis['no_motion_ratio']
        is_rhythmic = analysis['is_rhythmic']
        spasm_max = analysis['spasm_max']
        
        # Priority 1: No breathing detection (> 70% of window is silent)
        if no_motion_ratio > 0.7:
            return SleepState.NO_BREATHING
        
        # Priority 2: Check for sustained high movement (awake)
        if high_ratio > 0.5 and mean > self.MOVEMENT_THRESHOLD:
            return SleepState.AWAKE
        
        # Priority 3: Spasm detection - sudden spike during sleep
        if self.current_state in (SleepState.SLEEPING, SleepState.DEEP_SLEEP, SleepState.SPASM):
            if spasm_max > self.AWAKE_THRESHOLD and high_ratio < 0.3:
                # High spike but not sustained = spasm
                return SleepState.SPASM
        
        # Priority 4: Deep sleep - stable rhythmic breathing
        if is_rhythmic and mean < self.BREATHING_HIGH:
            return SleepState.DEEP_SLEEP
        
        # Priority 5: Light sleep - some movement but not awake
        if self.BREATHING_LOW < mean < self.AWAKE_THRESHOLD:
            return SleepState.SLEEPING
        
        # Priority 6: Very low movement but not zero = deep sleep
        if self.NO_MOTION_THRESHOLD < mean < self.BREATHING_HIGH:
            return SleepState.DEEP_SLEEP
        
        # Default: maintain current state
        return self.current_state if self.current_state != SleepState.UNKNOWN else SleepState.SLEEPING
    
    def _handle_transition(self, target_state: SleepState, 
                           current_time: float, analysis: Dict):
        """
        Handle state transitions with hysteresis (confirmation delays).
        """
        # Check if transition is valid
        if target_state not in self.VALID_TRANSITIONS.get(self.current_state, []):
            if target_state != self.current_state:
                # Invalid transition - try to find valid path
                target_state = self._find_valid_transition(target_state)
        
        # Same state - reset pending
        if target_state == self.current_state:
            # Special case: exit spasm back to previous state
            if self.current_state == SleepState.SPASM:
                if current_time - self.spasm_start_time > self.SPASM_WINDOW:
                    # Spasm window passed, return to sleep
                    self._execute_transition(self.pre_spasm_state or SleepState.SLEEPING, 
                                            current_time, "spasm_ended")
            self.pending_state = None
            self.pending_state_time = None
            return
        
        # Get required confirmation time for this transition
        confirm_time = self._get_confirmation_time(self.current_state, target_state)
        
        # Start or continue pending transition
        if self.pending_state == target_state:
            # Check if confirmation time has passed
            if current_time - self.pending_state_time >= confirm_time:
                self._execute_transition(target_state, current_time, "confirmed")
        else:
            # New pending state
            self.pending_state = target_state
            self.pending_state_time = current_time
            logger.debug(f"Pending transition: {self.current_state.value} -> {target_state.value} "
                        f"(need {confirm_time:.1f}s confirmation)")
    
    def _find_valid_transition(self, target_state: SleepState) -> SleepState:
        """Find a valid intermediate state for transition."""
        # From AWAKE, we can only go to SLEEPING first
        if self.current_state == SleepState.AWAKE and target_state == SleepState.DEEP_SLEEP:
            return SleepState.SLEEPING
        
        # From NO_BREATHING, any sleep state is valid
        if self.current_state == SleepState.NO_BREATHING:
            return target_state
        
        return self.current_state
    
    def _get_confirmation_time(self, from_state: SleepState, to_state: SleepState) -> float:
        """Get the required confirmation time for a state transition."""
        # Quick transitions (immediate or very fast)
        if to_state == SleepState.SPASM:
            return 0.5  # Spasms are detected quickly
        if to_state == SleepState.NO_BREATHING:
            return self.CONFIRM_NO_BREATHING_SECONDS
        
        # Transitions to awake need confirmation
        if to_state == SleepState.AWAKE:
            return self.CONFIRM_AWAKE_SECONDS
        
        # Transitions to deep sleep need breathing rhythm confirmation
        if to_state == SleepState.DEEP_SLEEP:
            return self.CONFIRM_DEEP_SLEEP_SECONDS
        
        # Transitions to light sleep from awake
        if from_state == SleepState.AWAKE and to_state == SleepState.SLEEPING:
            return self.CONFIRM_SLEEP_SECONDS
        
        # Default
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
        if old_state in (SleepState.SLEEPING, SleepState.DEEP_SLEEP) and new_state == SleepState.AWAKE:
            self.wake_up_count += 1
            if self.last_sleep_start is not None:
                sleep_duration = current_time - self.last_sleep_start
                self.events.append(SleepEvent("wake_up", current_time, {"sleep_duration": sleep_duration}))
                self.last_sleep_start = None
        
        # Track fell asleep
        if old_state in (SleepState.AWAKE, SleepState.UNKNOWN) and \
           new_state in (SleepState.SLEEPING, SleepState.DEEP_SLEEP):
            self.events.append(SleepEvent("fell_asleep", current_time))
            self.last_sleep_start = current_time
        
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
        # Update breathing detection time
        if self.current_state in (SleepState.SLEEPING, SleepState.DEEP_SLEEP, SleepState.SPASM):
            if self._last_update_time > 0:
                delta = current_time - self._last_update_time
                self.breathing_detected_seconds += delta
                
                # Also track sleep time
                if self.last_sleep_start is None:
                    self.last_sleep_start = current_time
                else:
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
            
            # Breathing quality
            breathing_quality = 0
            if session_duration > 0:
                breathing_quality = min(100, int(
                    (self.breathing_detected_seconds / session_duration) * 100
                ))
            
            # Breathing detected now
            breathing_now = self.current_state in (SleepState.SLEEPING, SleepState.DEEP_SLEEP)
            
            # Time in current state
            state_duration = current_time - self.state_start_time if self.state_start_time > 0 else 0
            
            return {
                "current_state": self.current_state.value,
                "breathing_detected": breathing_now,
                "state_duration_seconds": int(state_duration),
                "session_duration_minutes": int(session_duration / 60),
                "session_duration_seconds": int(session_duration),
                "total_sleep_minutes": int(self.total_sleep_seconds / 60),
                "total_sleep_seconds": int(self.total_sleep_seconds),
                "wake_ups": self.wake_up_count,
                "spasms": self.spasm_count,
                "breathing_quality_percent": breathing_quality,
                "last_motion_score": float(analysis.get('current_score', 0)),
                "motion_mean": float(analysis.get('mean', 0)),
                "motion_std": float(analysis.get('std', 0)),
                "is_rhythmic": analysis.get('is_rhythmic', False),
                "events_count": len(self.events),
                "pending_transition": self.pending_state.value if self.pending_state else None,
                "thresholds": {
                    "no_motion": self.NO_MOTION_THRESHOLD,
                    "breathing_low": self.BREATHING_LOW,
                    "breathing_high": self.BREATHING_HIGH,
                    "movement": self.MOVEMENT_THRESHOLD,
                    "awake": self.AWAKE_THRESHOLD
                }
            }
    
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
