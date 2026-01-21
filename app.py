import cv2
import time
import threading
import logging
import numpy as np
from flask import Flask, render_template, Response, jsonify, request
from sleep_manager import get_sleep_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('baby_sleep.log'),
        logging.StreamHandler()
    ]
)

# Suppress werkzeug (Flask) request logging for noisy endpoints
class StatusFilter(logging.Filter):
    def filter(self, record):
        # Filter out frequent polling requests
        msg = record.getMessage()
        if '/status' in msg or '/video_feed' in msg or '/sleep_stats' in msg:
            return False
        return True

werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.addFilter(StatusFilter())

app = Flask(__name__)

class MockCamera(object):
    """Simulates a camera feed for testing when no physical camera is available."""
    ALARM_TIMEOUT_SECONDS = 10  # Same as VideoCamera
    
    def __init__(self):
        self.motion_detected = False
        self.motion_score = 0
        self.frame_count = 0
        self.last_motion_time = time.time()
        print("Initializing Mock Camera (Simulation Mode)...")

    def get_frame(self):
        # Create a dynamic image
        self.frame_count += 1
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Draw a moving circle to simulate "motion" occasionally
        cx = int(320 + 100 * np.sin(self.frame_count * 0.1))
        cy = int(240 + 50 * np.cos(self.frame_count * 0.1))
        
        cv2.circle(img, (cx, cy), 40, (255, 255, 0), -1)
        cv2.putText(img, "SIMULATION MODE - NO CAMERA DETECTED", (50, 50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        # Simulate motion detection logic
        # In a real scenario, this would be calculated. Here we just fake it based on movement.
        self.motion_score = 8000 * abs(np.sin(self.frame_count * 0.1))
        self.motion_detected = self.motion_score > 5000
        
        # Update last_motion_time if motion is detected
        if self.motion_detected:
            self.last_motion_time = time.time()
        
        ret, jpeg = cv2.imencode('.jpg', img)
        return jpeg.tobytes()
    
    def is_alarm_active(self):
        """Check if alarm should be active (no motion for ALARM_TIMEOUT_SECONDS)."""
        return (time.time() - self.last_motion_time) > self.ALARM_TIMEOUT_SECONDS
    
    def get_seconds_since_motion(self):
        """Get the number of seconds since last motion was detected."""
        return int(time.time() - self.last_motion_time)

class VideoCamera(object):
    ALARM_TIMEOUT_SECONDS = 10  # Trigger alarm after 10 seconds of no motion
    PROCESSING_FPS = 5  # Process motion detection at 5 FPS in background
    
    def __init__(self):
        self.video = None
        self.last_frame = None
        self.motion_detected = False
        self.motion_score = 0
        self.roi = None  # Normalized ROI: (x, y, w, h) where values are 0.0-1.0
        self.lock = threading.Lock()
        self.last_motion_time = time.time()  # Track when motion was last detected
        
        # Enhancement settings
        self.zoom_level = 1.0  # 1.0 = no zoom, 2.0 = 2x zoom, etc.
        self.contrast_level = 1.0  # 1.0 = no enhancement, higher = more CLAHE
        self.brightness_level = 0  # -50 to +50 adjustment
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        
        # Background processing state
        self._running = False
        self._processing_thread = None
        self._latest_raw_frame = None  # Latest raw frame for display
        self._frame_lock = threading.Lock()
        self._motion_boxes = []  # Bounding boxes of detected motion areas
        
        try:
            with open("camera_debug.log", "w") as f:
                f.write("Starting camera init...\n")
                
            # We use CAP_DSHOW as it was confirmed working by diagnose_camera.py
            print("Attempting to open Camera Index 0 with CAP_DSHOW...")
            self.video = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            
            if not self.video.isOpened():
                params = (0, cv2.CAP_DSHOW)
                msg = f"Camera failed to open (isOpened() returned False). Params: {params}"
                print(msg)
                with open("camera_debug.log", "a") as f: f.write(msg + "\n")
                self.video = None
            else:
                # Try reading one frame to ensure it actually works
                ret, frame = self.video.read()
                if not ret:
                    msg = "Camera opened but failed to read first frame."
                    print(msg)
                    with open("camera_debug.log", "a") as f: f.write(msg + "\n")
                    self.video.release()
                    self.video = None
                else:
                    self.last_frame = self.process_frame(frame)
                    self._latest_raw_frame = frame.copy()
                    msg = "Camera initialized successfully!"
                    print(msg)
                    with open("camera_debug.log", "a") as f: f.write(msg + "\n")
                    
                    # Start background processing thread
                    self._start_background_processing()
                    
        except Exception as e:
            msg = f"CRITICAL ERROR initializing camera: {e}"
            print(msg)
            with open("camera_debug.log", "a") as f: f.write(msg + "\n")
            if self.video and self.video.isOpened():
                self.video.release()
            self.video = None
            
        # If we failed to get a real camera, we MUST NOT raise an exception here.
        # The get_camera() function will see self.video is None (or we handle it here)
        # But actually, the previous logic relied on an exception to switch to MockCamera.
        # We need to ensure logic flow handles failures without crashing.
    
    def _start_background_processing(self):
        """Start the background thread for continuous motion detection."""
        if self._running:
            return
        self._running = True
        self._processing_thread = threading.Thread(target=self._background_loop, daemon=True)
        self._processing_thread.start()
        print("Background motion detection thread started.")
    
    def _stop_background_processing(self):
        """Stop the background processing thread."""
        self._running = False
        if self._processing_thread and self._processing_thread.is_alive():
            self._processing_thread.join(timeout=2.0)
        print("Background motion detection thread stopped.")
    
    def _background_loop(self):
        """
        Continuous loop that captures frames and processes motion detection.
        This runs independently of whether any client is viewing the stream.
        """
        frame_interval = 1.0 / self.PROCESSING_FPS
        
        while self._running:
            start_time = time.time()
            
            try:
                with self.lock:
                    if not self.video or not self.video.isOpened():
                        break
                    ret, frame = self.video.read()
                
                if ret and frame is not None:
                    # Store raw frame for display
                    with self._frame_lock:
                        self._latest_raw_frame = frame.copy()
                    
                    # Process for motion detection
                    self._process_motion(frame)
                    
                    # Update sleep manager with current motion score
                    sleep_mgr = get_sleep_manager()
                    sleep_mgr.update(self.motion_score)
                    
            except Exception as e:
                print(f"Error in background processing: {e}")
            
            # Maintain target FPS
            elapsed = time.time() - start_time
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)
    
    def _process_motion(self, frame):
        """Process a frame for motion detection (updates motion state)."""
        h, w = frame.shape[:2]
        current_gray = self.process_frame(frame)
        
        if self.last_frame is None:
            self.last_frame = current_gray
            return
        
        # Compute difference
        frame_delta = cv2.absdiff(self.last_frame, current_gray)
        # Tune sensitivity for breathing detection
        thresh = cv2.threshold(frame_delta, 5, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        
        # Apply ROI mask if set
        if self.roi is not None:
            rx, ry, rw, rh = self.roi
            roi_x = int(rx * w)
            roi_y = int(ry * h)
            roi_w = int(rw * w)
            roi_h = int(rh * h)
            
            mask = np.zeros(thresh.shape, dtype=np.uint8)
            mask[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w] = 255
            thresh = cv2.bitwise_and(thresh, mask)
        
        # Calculate motion score (sum of white pixels)
        self.motion_score = np.sum(thresh)
        self.motion_detected = self.motion_score > 500
        
        # Find contours and save bounding boxes for display
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for contour in contours:
            if cv2.contourArea(contour) > 100:  # Filter small noise
                boxes.append(cv2.boundingRect(contour))
        self._motion_boxes = boxes
        
        # Update last_motion_time if motion is detected
        if self.motion_detected:
            self.last_motion_time = time.time()
        
        # Update last frame
        self.last_frame = current_gray
    
    def is_working(self):
        return self.video is not None and self.video.isOpened()

    def apply_enhancements(self, frame):
        """Apply contrast, brightness and CLAHE enhancements for display."""
        if self.contrast_level > 1.0 or self.brightness_level != 0:
            # Convert to LAB color space for better contrast handling
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            
            # Apply CLAHE with variable clip limit based on contrast level
            clip_limit = 2.0 * self.contrast_level
            clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
            l = clahe.apply(l)
            
            # Apply brightness adjustment
            if self.brightness_level != 0:
                l = cv2.add(l, self.brightness_level)
            
            # Merge and convert back
            lab = cv2.merge([l, a, b])
            frame = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        
        return frame

    def apply_zoom(self, frame, roi_pixel=None):
        """Apply digital zoom to frame, centered on ROI if available."""
        if self.zoom_level <= 1.0:
            return frame
        
        h, w = frame.shape[:2]
        
        # Determine zoom center
        if roi_pixel is not None:
            rx, ry, rw, rh = roi_pixel
            center_x = rx + rw // 2
            center_y = ry + rh // 2
        else:
            center_x = w // 2
            center_y = h // 2
        
        # Calculate zoomed region size
        zoom_w = int(w / self.zoom_level)
        zoom_h = int(h / self.zoom_level)
        
        # Calculate crop bounds, keeping center in view
        x1 = max(0, center_x - zoom_w // 2)
        y1 = max(0, center_y - zoom_h // 2)
        x2 = min(w, x1 + zoom_w)
        y2 = min(h, y1 + zoom_h)
        
        # Adjust if we hit the edge
        if x2 == w:
            x1 = w - zoom_w
        if y2 == h:
            y1 = h - zoom_h
        
        # Ensure bounds are valid
        x1 = max(0, x1)
        y1 = max(0, y1)
        
        # Crop and resize back to original size
        cropped = frame[y1:y2, x1:x2]
        zoomed = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
        
        return zoomed

    def process_frame(self, frame):
        """Process frame for motion detection (grayscale + blur)."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Apply CLAHE for better motion detection in low-light
        gray = self.clahe.apply(gray)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        return gray

    def get_frame(self):
        """
        Get the latest frame for display.
        Motion detection is handled by the background thread.
        This method only handles display rendering (overlays, enhancements, zoom).
        """
        # Get the latest frame from background thread
        with self._frame_lock:
            if self._latest_raw_frame is None:
                return None
            frame = self._latest_raw_frame.copy()
        
        h, w = frame.shape[:2]
        
        # Calculate ROI pixel coordinates for display
        roi_pixel = None
        if self.roi is not None:
            rx, ry, rw, rh = self.roi
            roi_x = int(rx * w)
            roi_y = int(ry * h)
            roi_w = int(rw * w)
            roi_h = int(rh * h)
            roi_pixel = (roi_x, roi_y, roi_w, roi_h)

        # Draw on frame for debug/feed
        status_color = (0, 255, 0) if self.motion_detected else (0, 0, 255)
        
        # Draw ROI rectangle if set
        if roi_pixel is not None:
            roi_x, roi_y, roi_w, roi_h = roi_pixel
            cv2.rectangle(frame, (roi_x, roi_y), (roi_x + roi_w, roi_y + roi_h), (255, 255, 0), 2)
        
        # Draw motion bounding boxes (calculated by background thread)
        for (x, y, bw, bh) in self._motion_boxes:
            cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 255, 0), 2)

        cv2.putText(frame, f"Motion: {int(self.motion_score)}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
        
        # Apply visual enhancements
        frame = self.apply_enhancements(frame)
        
        # Apply digital zoom
        frame = self.apply_zoom(frame, roi_pixel)
        
        # Show zoom/enhancement info overlay
        info_texts = []
        if self.zoom_level > 1.0:
            info_texts.append(f"Zoom: {self.zoom_level:.1f}x")
        if self.contrast_level > 1.0:
            info_texts.append(f"Contrast: {self.contrast_level:.1f}")
        if self.brightness_level != 0:
            info_texts.append(f"Bright: {self.brightness_level:+d}")
        
        if info_texts:
            info_str = " | ".join(info_texts)
            cv2.putText(frame, info_str, (10, frame.shape[0] - 15), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                   
        ret, jpeg = cv2.imencode('.jpg', frame)
        return jpeg.tobytes()

    def is_alarm_active(self):
        """Check if alarm should be active (no motion for ALARM_TIMEOUT_SECONDS)."""
        return (time.time() - self.last_motion_time) > self.ALARM_TIMEOUT_SECONDS
    
    def get_seconds_since_motion(self):
        """Get the number of seconds since last motion was detected."""
        return int(time.time() - self.last_motion_time)

    def __del__(self):
        self._stop_background_processing()
        if self.video and self.video.isOpened():
            self.video.release()

camera = None
camera_lock = threading.Lock()

def get_camera():
    global camera
    with camera_lock:
        if camera is None:
            print("Initializing camera for the first time...")
            # Try to create the real camera object
            try:
                 real_cam = VideoCamera()
                 if real_cam.is_working():
                     camera = real_cam
                     print("Using Real VideoCamera.")
                 else:
                     print("Real Camera init failed (logic). Falling back to MockCamera.")
                     camera = MockCamera()
            except Exception as e:
                print(f"Exception during Camera instantiation: {e}")
                print("Falling back to MockCamera.")
                camera = MockCamera()
            
    return camera

@app.route('/')
def index():
    return render_template('index.html')

def gen(camera):
    while True:
        frame = camera.get_frame()
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
        else:
            time.sleep(0.1)

@app.route('/video_feed')
def video_feed():
    return Response(gen(get_camera()),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    cam = get_camera()
    return jsonify({
        'motion_detected': bool(cam.motion_detected),
        'motion_score': float(cam.motion_score),
        'alarm_active': cam.is_alarm_active(),
        'seconds_since_motion': cam.get_seconds_since_motion()
    })

@app.route('/set_roi', methods=['POST'])
def set_roi():
    """Set the Region of Interest for motion detection."""
    cam = get_camera()
    data = request.get_json()
    if data and all(k in data for k in ['x', 'y', 'w', 'h']):
        x = float(data['x'])
        y = float(data['y'])
        w = float(data['w'])
        h = float(data['h'])
        # Basic validation
        if 0 <= x <= 1 and 0 <= y <= 1 and w > 0 and h > 0:
            cam.roi = (x, y, w, h)
            print(f"ROI set to: {cam.roi}")
            return jsonify({'status': 'ok', 'roi': cam.roi})
    return jsonify({'status': 'error', 'message': 'Invalid ROI data'}), 400

@app.route('/reset_roi', methods=['POST'])
def reset_roi():
    """Clear the Region of Interest."""
    cam = get_camera()
    cam.roi = None
    print("ROI cleared.")
    return jsonify({'status': 'ok'})

@app.route('/set_enhancements', methods=['POST'])
def set_enhancements():
    """Set zoom, contrast, and brightness enhancement levels."""
    cam = get_camera()
    data = request.get_json()
    
    if not data:
        return jsonify({'status': 'error', 'message': 'No data provided'}), 400
    
    # Update only provided values
    if 'zoom' in data:
        zoom = float(data['zoom'])
        if 1.0 <= zoom <= 4.0:
            cam.zoom_level = zoom
            print(f"Zoom set to: {zoom}")
        else:
            return jsonify({'status': 'error', 'message': 'Zoom must be between 1.0 and 4.0'}), 400
    
    if 'contrast' in data:
        contrast = float(data['contrast'])
        if 1.0 <= contrast <= 3.0:
            cam.contrast_level = contrast
            print(f"Contrast set to: {contrast}")
        else:
            return jsonify({'status': 'error', 'message': 'Contrast must be between 1.0 and 3.0'}), 400
    
    if 'brightness' in data:
        brightness = int(data['brightness'])
        if -50 <= brightness <= 50:
            cam.brightness_level = brightness
            print(f"Brightness set to: {brightness}")
        else:
            return jsonify({'status': 'error', 'message': 'Brightness must be between -50 and 50'}), 400
    
    return jsonify({
        'status': 'ok',
        'zoom': cam.zoom_level,
        'contrast': cam.contrast_level,
        'brightness': cam.brightness_level
    })

@app.route('/get_settings')
def get_settings():
    """Get current camera enhancement settings."""
    cam = get_camera()
    
    # Handle MockCamera which doesn't have enhancement settings
    if isinstance(cam, MockCamera):
        return jsonify({
            'zoom': 1.0,
            'contrast': 1.0,
            'brightness': 0,
            'has_roi': False,
            'roi': None
        })
    
    return jsonify({
        'zoom': cam.zoom_level,
        'contrast': cam.contrast_level,
        'brightness': cam.brightness_level,
        'has_roi': cam.roi is not None,
        'roi': cam.roi
    })

@app.route('/reset_enhancements', methods=['POST'])
def reset_enhancements():
    """Reset all enhancements to default values."""
    cam = get_camera()
    
    if isinstance(cam, VideoCamera):
        cam.zoom_level = 1.0
        cam.contrast_level = 1.0
        cam.brightness_level = 0
        print("Enhancements reset to defaults.")
    
    return jsonify({'status': 'ok'})


# ==================== Sleep Monitoring Endpoints ====================

@app.route('/sleep_stats')
def sleep_stats():
    """Get current sleep monitoring statistics."""
    sleep_mgr = get_sleep_manager()
    return jsonify(sleep_mgr.get_stats())


@app.route('/sleep_events')
def sleep_events():
    """Get recent sleep events (wake ups, fell asleep, etc.)."""
    sleep_mgr = get_sleep_manager()
    count = request.args.get('count', 10, type=int)
    return jsonify({
        'events': sleep_mgr.get_recent_events(count)
    })


@app.route('/sleep_thresholds', methods=['GET', 'POST'])
def sleep_thresholds():
    """Get or set sleep detection thresholds."""
    sleep_mgr = get_sleep_manager()
    
    if request.method == 'POST':
        data = request.get_json() or {}
        sleep_mgr.set_thresholds(
            breathing_min=data.get('breathing_min'),
            breathing_max=data.get('breathing_max'),
            awake_threshold=data.get('awake_threshold')
        )
        return jsonify({'status': 'ok', 'thresholds': sleep_mgr.get_stats()['thresholds']})
    
    return jsonify(sleep_mgr.get_stats()['thresholds'])


@app.route('/sleep_session', methods=['POST'])
def sleep_session():
    """Start or stop a sleep monitoring session."""
    sleep_mgr = get_sleep_manager()
    data = request.get_json() or {}
    action = data.get('action', 'start')
    
    if action == 'start':
        sleep_mgr.start_session()
        return jsonify({'status': 'ok', 'message': 'Session started'})
    elif action == 'stop':
        sleep_mgr.stop_session()
        return jsonify({'status': 'ok', 'message': 'Session stopped', 'stats': sleep_mgr.get_stats()})
    else:
        return jsonify({'status': 'error', 'message': 'Unknown action'}), 400


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)

