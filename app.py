import cv2
import time
import threading
import numpy as np
from flask import Flask, render_template, Response, jsonify

app = Flask(__name__)

class MockCamera(object):
    """Simulates a camera feed for testing when no physical camera is available."""
    def __init__(self):
        self.motion_detected = False
        self.motion_score = 0
        self.frame_count = 0
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
        
        ret, jpeg = cv2.imencode('.jpg', img)
        return jpeg.tobytes()

class VideoCamera(object):
    def __init__(self):
        self.video = cv2.VideoCapture(0, cv2.CAP_DSHOW) # CAP_DSHOW often helps on Windows
        self.last_frame = None
        self.motion_detected = False
        self.motion_score = 0
        
        # Check if camera opened successfully
        if not self.video.isOpened():
            raise RuntimeError("Could not exist video source.")
            
        # Warmup
        ret, frame = self.video.read()
        if ret:
            self.last_frame = self.process_frame(frame)
        else:
             raise RuntimeError("Could not read frame from video source.")

    def process_frame(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        return gray

    def get_frame(self):
        ret, frame = self.video.read()
        if not ret:
            return None
            
        current_gray = self.process_frame(frame)
        
        if self.last_frame is None:
            self.last_frame = current_gray
            
        # Compute difference
        frame_delta = cv2.absdiff(self.last_frame, current_gray)
        thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        
        # Calculate motion score (sum of white pixels)
        self.motion_score = np.sum(thresh)
        self.motion_detected = self.motion_score > 5000 # Threshold, tune later
        
        # Update last frame
        self.last_frame = current_gray

        # Draw on frame for debug/feed
        status_color = (0, 255, 0) if self.motion_detected else (0, 0, 255)
        cv2.putText(frame, f"Motion: {self.motion_score}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
                   
        # Resize for performance if needed, but 640x480 is standard
        
        ret, jpeg = cv2.imencode('.jpg', frame)
        return jpeg.tobytes()

    def __del__(self):
        if self.video.isOpened():
            self.video.release()

camera = None

def get_camera():
    global camera
    if camera is None:
        try:
            camera = VideoCamera()
            print("Camera initialized successfully.")
        except Exception as e:
            print(f"Error initializing camera: {e}")
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
        'motion_score': float(cam.motion_score)
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
