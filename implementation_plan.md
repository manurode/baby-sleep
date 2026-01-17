# Baby Monitor Implementation Plan

## Objective
Build a web-based baby monitor application that uses a webcam to detect breathing/movement and displays it on a premium user interface.

## Tech Stack
- **Backend**: Python (Flask) for video processing and streaming.
- **Computer Vision**: OpenCV (`cv2`) for movement detection.
- **Frontend**: HTML5, Vanilla CSS (Premium Design), JavaScript.
- **Communication**: MJPEG streaming for video, REST/polling for status updates.
- **Mobile**: Native Android App (Kotlin) for background monitoring and notifications.

## Phase 1: Environment & Setup
- [x] Create virtual environment (`venv`)
- [x] Install dependencies (`opencv-python`, `flask`, `numpy`)
- [x] Create project structure

## Phase 2: Backend Development (`app.py`)
- [x] Implement video capture loop using OpenCV.
- [x] Implement robust movement detection (e.g., Frame differencing).
- [x] Create a focused ROI (Region of Interest) mechanism.
- [x] Set up Flask server to stream video feed.
- [x] Expose an endpoint for "current status" (Movement detected: Yes/No).

## Phase 3: Frontend Development
- [x] Design a beautiful, responsive dashboard.
- [x] Display live video feed.
- [x] Visual indicator for movement (e.g., a glowing ring or dynamic graph).
- [x] Alert system (Visual) when no movement is detected (Simulating breath holding/apnea - careful with medical claims, keep it simple "Movement" vs "No Movement").

## Phase 4: Refinement
- [x] Tune sensitivity of motion detection.
- [x] Polish UI animations.

## Phase 5: Enhanced Breathing Detection (Zoom & Contrast)
- [x] Add digital zoom feature (1x to 4x) centered on ROI
- [x] Implement CLAHE (Contrast Limited Adaptive Histogram Equalization) for night vision improvement
- [x] Add brightness adjustment (-50 to +50)
- [x] Create premium UI slider controls for real-time adjustments
- [x] Add API endpoints for enhancement settings (`/set_enhancements`, `/get_settings`, `/reset_enhancements`)
- [x] Display enhancement info overlay on video feed

## Phase 6: Android App & Centralized Alarm Logic

### Goal
Allow monitoring the baby's status via a dedicated Android App that can run in the background and issue system notifications when breathing stops (no movement detected). Currently, this logic resides in the web browser, which stops working if the phone screen turns off or the browser is backgrounded.

### Backend Changes (Python/Flask)
- [x] Move the "10 seconds no movement" timer from `main.js` to `app.py`
- [x] Add `last_motion_time` timestamp tracking in VideoCamera class
- [x] Add `last_motion_time` tracking in MockCamera class
- [x] Update `get_frame()` to update timestamp when motion_score > threshold
- [x] Add `is_alarm_active()` method: returns True if `(now - last_motion_time) > 10 seconds`
- [x] Add `get_seconds_since_motion()` method
- [x] Update `/status` route to include `alarm_active` and `seconds_since_motion` in JSON response

### Frontend Changes (Web)
- [x] Remove local `lastMovementTime` and `setTimeout` logic for the alarm
- [x] Update `fetchStatus()` to read `alarm_active` from the server response
- [x] Trigger UI Red Alert/Sound based on server `alarm_active` state

### Android App (New Project)
- [x] Create Android Studio project structure (Kotlin)
- [x] Configure Gradle with dependencies (OkHttp, Gson)
- [x] Create AndroidManifest with permissions:
  - [x] INTERNET, FOREGROUND_SERVICE, POST_NOTIFICATIONS, VIBRATE, WAKE_LOCK
- [x] Implement MainActivity with WebView for full web interface
- [x] Implement MonitoringService (ForegroundService) for background polling
- [x] Implement high-priority notification channel for alarms
- [x] Implement vibration and sound alerts
- [x] Create SettingsActivity for server URL configuration
- [x] Create BootReceiver for optional auto-start on device boot
- [x] Design premium dark theme matching web interface
- [x] Create comprehensive README with build instructions

### Verification Plan
- [x] **Automated Tests**: Use curl to query `/status` while blocking the camera (or using Mock Camera) to verify `alarm_active` switches to true after 10 seconds.
  - ✅ Tested with curl - `/status` returns `alarm_active: true` when no motion detected for 10+ seconds
- [x] **Manual Verification - Backend**: Cover camera → Wait 10s → Check `/status` JSON in browser.
  - ✅ Confirmed JSON response includes `alarm_active` and `seconds_since_motion` fields
- [x] **Manual Verification - Web**: Verify the red screen still appears correctly.
  - ✅ Tested in browser - Red alarm screen with "ALARM: NO MOVEMENT DETECTED!" text works correctly
- [ ] **Manual Verification - Android**:
  - [ ] Build and install the app.
  - [ ] Close the app (Home button).
  - [ ] Stop movement in front of camera.
  - [ ] Verify Android System Notification appears.
  - ⚠️ Requires Android Studio + physical device to test

---

## Notes

### Server URL Format
The Android app connects to the Flask server using: `http://<IP_ADDRESS>:5000`

For example: `http://192.168.1.100:5000`

### API Response Format
The `/status` endpoint now returns:
```json
{
    "motion_detected": true,
    "motion_score": 1234.5,
    "alarm_active": false,
    "seconds_since_motion": 2
}
```
