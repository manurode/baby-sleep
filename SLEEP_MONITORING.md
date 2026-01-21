# Sleep Monitoring System

## Overview
This document describes the advanced sleep monitoring system implemented for the Baby Sleep Monitor application. The system has been upgraded from simple threshold-based detection to a **sliding window statistical analysis** engine, designed to differentiate between actual wakefulness, sleep spasms, and stable breathing patterns.

## Core Logic: Sliding Window Analysis

Instead of analyzing instantaneous frames, the system maintains a **60-second buffer** of motion scores. 
Every update cycle, it analyzes the last **10 seconds** of data to calculate:
- **Mean Motion**: The average intensity of movement.
- **Standard Deviation**: How much the movement varies (crucial for breathing rhythm).
- **Peak Score**: The maximum motion spike in the window.
- **Density Ratios**: Percentage of time with high movement vs. no movement.

### State Classification Priorities
The system determines the state based on a priority waterfall:

1.  **⚠️ NO BREATHING**: If >70% of the window has effectively zero motion (< 50k).
2.  **👀 AWAKE**: Sustained high movement (> 3M) with high density.
3.  **💢 SPASM**: A sudden spike (> 3M) that is *not* sustained (short duration).
4.  **� SLEEPING**: Normal sleep state. Covers both stable breathing (low motion) and light movement (moderate motion).

---

## Sleep States & Thresholds

| State | Emoji | Condition (Simplified) | Description |
|-------|-------|------------------------|-------------|
| **No Breathing** | ⚠️ | Motion < 50,000 | Critical alert. No movement detected for extended time. |
| **Sleeping** | � | 100k < Motion < 3M | Normal sleep. Includes rhythmic breathing and light movement. |
| **Spasm** | 💢 | Spike > 3M (Short) | Sudden jerk or movement returning to sleep quickly. |
| **Awake** | 👀 | Motion > 3M (Sustained) | Active, continuous movement. Baby is likely up. |

### Calibrated Thresholds
*Values based on MEAN of accumulated pixel difference scores over 10-second window.*

- **No Motion (Mean)**: `< 10,000` → Triggers NO_BREATHING alert
- **Breathing Range (Mean)**: `10,000` - `1,500,000`
- **Active Movement (Mean)**: `> 5,000,000`
- **Awake Peak (Mean)**: `> 10,000,000`

**Note**: Individual frames often have `Motion Score: 0` due to camera frame processing. The system now uses the **mean of the window** instead of counting individual zero frames.

---

## Hysteresis & State Confirmation

To prevent "state flickering" (e.g., rapid switching between Sleep/Awake), the system requires states to be **confirmed** over time before transitioning.

| Transition To | Confirmation Time | Reason |
|---------------|------------------|--------|
| **Awake** | **8.0 seconds** | Filters out short movements; ensures baby is truly active. |
| **Sleeping** | **15.0 seconds** | Requires a period of calm to confirm baby has settled back down. |
| **No Breathing**| **12.0 seconds** | Avoids false alarms from momentary stillness. |
| **Spasm** | **0.5 seconds** | Detected immediately to differentiate from waking up. |

---

## Metrics & Analytics

The backend calculates the following metrics in real-time:

- **Breathing Quality %**: Percentage of session time where valid breathing motion was detected.
- **Wake Ups**: Number of confirmed transitions from Sleep → Awake.
- **Spasms**: Number of detected short-term movement spikes during sleep.
- **Rhythm Detection**: Boolean flag indicating if the current motion follows a breathing pattern (low standard deviation).

---

## API Reference

### `GET /sleep_stats`

Returns the current monitoring status and cumulative metrics.

**Response Example:**
```json
{
    "current_state": "sleeping",
    "breathing_detected": true,
    "state_duration_seconds": 450,
    
    "session_duration_minutes": 120,
    "total_sleep_minutes": 115,
    "wake_ups": 1,
    "spasms": 3,
    "breathing_quality_percent": 98,
    
    "last_motion_score": 850400.0,
    "motion_mean": 820000.0,
    "motion_std": 45000.0,
    "is_rhythmic": true,
    
    "pending_transition": null,
    
    "thresholds": {
        "no_motion": 50000,
        "breathing_low": 100000,
        "breathing_high": 1500000,
        "movement": 2000000,
        "awake": 3000000
    }
}
```

---

## User Guide: Interpretation

- **If "No Breathing" appears often**: 
  - Check camera framing. Ensure specific ROI is set on the baby's chest.
  - If false alarms persist, `NO_MOTION_THRESHOLD` might need lowering.

- **If "Awake" triggers too easily**:
  - `AWAKE_THRESHOLD` might need to be increased.
  - The confirmation time (8s) filters out tossing and turning.

- **"Spasm" vs "Awake"**:
  - A **Spasm** is an isolated event (e.g., 2 seconds of movement). The state returns to "Sleeping" automatically.
  - **Awake** is a state change. It requires the baby to keep moving.
