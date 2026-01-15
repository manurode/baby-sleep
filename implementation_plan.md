# Baby Monitor Implementation Plan

## Objective
Build a web-based baby monitor application that uses a webcam to detect breathing/movement and displays it on a premium user interface.

## Tech Stack
- **Backend**: Python (Flask) for video processing and streaming.
- **Computer Vision**: OpenCV (`cv2`) for movement detection.
- **Frontend**: HTML5, Vanilla CSS (Premium Design), JavaScript.
- **Communication**: MJPEG streaming for video, REST/polling for status updates.

## Phase 1: Environment & Setup
- [x] Create virtual environment (`venv`)
- [x] Install dependencies (`opencv-python`, `flask`, `numpy`)
- [x] Create project structure

## Phase 2: Backend Development (`app.py`)
- [x] Implement video capture loop using OpenCV.
- [x] Implement robust movement detection (e.g., Frame differencing).
- [ ] Create a focused ROI (Region of Interest) mechanism (optional for MVP, but good for "abdominal" specific monitoring).
- [x] Set up Flask server to stream video feed.
- [x] Expose an endpoint for "current status" (Movement detected: Yes/No).

## Phase 3: Frontend Development
- [x] Design a beautiful, responsive dashboard.
- [x] Display live video feed.
- [x] Visual indicator for movement (e.g., a glowing ring or dynamic graph).
- [x] Alert system (Visual) when no movement is detected (Simulating breath holding/apnea - careful with medical claims, keep it simple "Movement" vs "No Movement").

## Phase 4: Refinement
- [ ] Tune sensitivity of motion detection.
- [ ] Polish UI animations.
