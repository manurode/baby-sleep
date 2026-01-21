# Sleep Monitoring System

## Overview

This document describes the advanced sleep monitoring system for the Baby Sleep Monitor application. The system uses computer vision to detect breathing patterns and provides scientifically-backed sleep quality analysis based on research about infant sleep cycles.

## Scientific Background

### Baby Sleep Cycles

Babies have shorter sleep cycles than adults (~50-60 minutes) with two main phases:

1. **Quiet Sleep (Deep Sleep / Non-REM)**
   - Most restorative physically; growth hormone is secreted
   - **Breathing pattern**: Very regular and rhythmic
   - **Detection**: Low variability in inter-breath intervals
   - Movement: Almost none, only chest

2. **Active Sleep (Light Sleep / REM)**
   - Crucial for brain development and memory consolidation
   - **Breathing pattern**: Irregular, may include periodic breathing (common in babies)
   - **Detection**: High variability in inter-breath intervals
   - Movement: Spasms, facial expressions, twitching

### Normal Breathing Rates

- Babies normally breathe **30-60 times per minute**
- 2-second intervals = 30 BPM (normal, deep sleep)
- 1.5-second intervals = 40 BPM (normal, active sleep)
- 5-second intervals = 12 BPM (unusually slow, potential alert)

---

## System Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────┐
│                    SleepManager                         │
│  ┌─────────────────┐    ┌─────────────────────────────┐ │
│  │ BreathingAnalyzer│    │ State Machine              │ │
│  │ - Peak detection │    │ - UNKNOWN                  │ │
│  │ - Interval calc  │    │ - NO_BREATHING (alert)     │ │
│  │ - Rate (BPM)     │    │ - DEEP_SLEEP (quiet)       │ │
│  │ - Variability    │    │ - LIGHT_SLEEP (REM)        │ │
│  │ - Phase detection│    │ - SPASM                    │ │
│  └─────────────────┘    │ - AWAKE                    │ │
│                          └─────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ Metrics & Reports                                   │ │
│  │ - Total/Deep/Light sleep duration                   │ │
│  │ - Wake-ups, spasms, sleep cycles                    │ │
│  │ - Breathing rate & variability                      │ │
│  │ - Sleep quality score (0-100)                       │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Breathing Analyzer

The `BreathingAnalyzer` class detects breathing patterns by:

1. **Peak Detection**: Identifies motion peaks above threshold as breaths
2. **Interval Calculation**: Measures time between consecutive breaths
3. **Rate Calculation**: Converts intervals to breaths per minute (BPM)
4. **Variability Analysis**: Calculates coefficient of variation (CV = std/mean)

#### Variability Thresholds

| Variability (CV) | Sleep Phase | Description |
|------------------|-------------|-------------|
| < 15% | Deep Sleep | Regular, rhythmic breathing |
| 15% - 30% | Transitional | Between phases |
| > 30% | Light/REM Sleep | Irregular, variable breathing |

---

## Sleep States

| State | Emoji | Condition | Description |
|-------|-------|-----------|-------------|
| **NO_BREATHING** | ⚠️ | Mean motion < 10,000 | Critical alert - no movement detected |
| **DEEP_SLEEP** | 💤 | Low variability (<15%) | Quiet sleep with regular breathing |
| **LIGHT_SLEEP** | 😴 | High variability (>15%) | Active/REM sleep with irregular breathing |
| **SPASM** | 💢 | Sudden spike during sleep | Normal sleep movements (twitches) |
| **AWAKE** | 👀 | Sustained high motion | Baby is awake and active |

### State Transition Diagram

```
    ┌──────────────────────────────────────────────┐
    │                                              │
    ▼                                              │
UNKNOWN ──────► DEEP_SLEEP ◄──────► LIGHT_SLEEP ◄─┤
    │              │    ▲              │    ▲      │
    │              │    │              │    │      │
    │              ▼    │              ▼    │      │
    │           SPASM ──┼────────► SPASM ──┘      │
    │              │                   │           │
    │              ▼                   ▼           │
    └──────────► AWAKE ◄──────────────────────────┘
                   │
                   ▼
             NO_BREATHING
```

---

## Hysteresis (Confirmation Times)

To prevent state flickering, transitions require sustained confirmation:

| Transition | Confirmation Time | Reason |
|------------|------------------|--------|
| → AWAKE | 8 seconds | Ensures baby is truly active |
| → SLEEP (from awake) | 15 seconds | Confirms baby has settled |
| → NO_BREATHING | 12 seconds | Avoids false alarms |
| → DEEP ↔ LIGHT | 30 seconds | Sleep phases change slowly |
| → SPASM | 0.5 seconds | Quick detection for logging |

---

## Sleep Quality Scoring

The system calculates a **Sleep Quality Score (0-100)** based on:

### Factors

1. **Deep Sleep Ratio** (target: 35-50% for babies)
   - < 20%: -20 points
   - 20-35%: -10 points
   - 35-60%: No penalty (optimal)
   - > 60%: -5 points (unusual)

2. **Wake-ups** (expected: ~1 per hour is normal)
   - Each extra wake-up: -10 points (max -30)

3. **Spasms** (normal during REM, but excessive = restless)
   - > 10 spasms: -1 point each (max -10)

4. **Breathing Variability**
   - Very high (>40%): -10 points (restless breathing)

### Quality Ratings

| Score | Rating |
|-------|--------|
| 85-100 | Excellent |
| 70-84 | Good |
| 50-69 | Fair |
| 30-49 | Poor |
| 0-29 | Very Poor |

---

## API Reference

### `GET /sleep_stats`

Returns current monitoring status and cumulative metrics.

**Response:**
```json
{
    "current_state": "deep_sleep",
    "breathing_detected": true,
    "state_duration_seconds": 450,
    
    "session_duration_minutes": 120,
    "total_sleep_minutes": 115,
    "deep_sleep_minutes": 55,
    "light_sleep_minutes": 60,
    
    "sleep_quality_score": 82,
    "deep_sleep_percent": 48,
    "light_sleep_percent": 52,
    
    "wake_ups": 1,
    "spasms": 3,
    "sleep_cycles_completed": 2,
    
    "breathing_rate_bpm": 38.5,
    "breathing_variability": 0.12,
    "breathing_phase": "deep",
    "breaths_detected": 1250,
    
    "last_motion_score": 125000.0,
    "motion_mean": 95000.0,
    "motion_std": 45000.0
}
```

### `GET /sleep_report`

Returns a comprehensive, parent-friendly sleep report.

**Response:**
```json
{
    "report_generated_at": 1737474000.0,
    
    "summary": {
        "total_sleep": "1h 55m",
        "quality_score": 82,
        "quality_rating": "Good"
    },
    
    "sleep_breakdown": {
        "deep_sleep": "55m (48%)",
        "light_sleep": "60m (52%)",
        "description": "Good balance of deep and light sleep. Deep sleep promotes physical growth."
    },
    
    "events_summary": {
        "wake_ups": 1,
        "spasms": 3,
        "sleep_cycles": 2,
        "average_cycle_minutes": 57.5
    },
    
    "breathing": {
        "average_rate_bpm": 38.5,
        "status": "normal",
        "variability": 12.0,
        "current_phase": "deep"
    },
    
    "raw_stats": { ... }
}
```

### `GET /sleep_events`

Returns recent sleep events for timeline display.

**Parameters:**
- `count` (optional, default=10): Number of events to return

**Response:**
```json
{
    "events": [
        {"type": "fell_asleep", "timestamp": 1737470400.0, "data": {}},
        {"type": "phase_change", "timestamp": 1737471800.0, "data": {"from": "light", "to": "deep"}},
        {"type": "spasm", "timestamp": 1737472100.0, "data": {}},
        {"type": "wake_up", "timestamp": 1737474000.0, "data": {"sleep_duration": 3600}}
    ]
}
```

---

## Calibration

### Motion Thresholds

| Threshold | Value | Description |
|-----------|-------|-------------|
| NO_MOTION | < 10,000 | Triggers NO_BREATHING alert |
| BREATHING_LOW | 10,000 | Minimum for breath detection |
| BREATHING_HIGH | 1,500,000 | Maximum for sleep movement |
| MOVEMENT | 5,000,000 | Active movement detected |
| AWAKE | 10,000,000 | Very active movement |

### Breathing Detection

| Threshold | Value | Description |
|-----------|-------|-------------|
| BREATH_PEAK | 50,000 | Minimum motion for breath detection |
| MIN_INTERVAL | 1.0s | Maximum 60 BPM |
| MAX_INTERVAL | 5.0s | Minimum 12 BPM |

---

## Interpreting Results for Parents

### "No Breathing" Alerts
- Check camera framing (ROI should be on baby's chest)
- Ensure there's no obstruction
- If persistent, check on baby immediately

### Low Deep Sleep Percentage
- Baby may be in REM-heavy phase (normal in early months)
- Check room temperature and noise levels
- Consider sleep environment adjustments

### High Spasm Count
- Normal during REM sleep (dreaming)
- If excessive with wake-ups, may indicate discomfort

### Breathing Rate Outside Normal Range
- **Slow (<25 BPM)**: May indicate very deep sleep or sensor issue
- **Fast (>60 BPM)**: Could indicate fever, heat, or start of illness
