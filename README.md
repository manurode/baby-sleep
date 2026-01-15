# Baby Sleep Monitor

A premium, AI-powered baby movement monitor application. This tool uses your computer's webcam to detect motion (specifically breathing movements) and provides a real-time dashboard with visual feedback.

![UI Preview](https://via.placeholder.com/800x400?text=Premium+UI+Preview)

## Features

- **Real-time Video Feed**: Low-latency MJPEG streaming.
- **Motion Detection**: Advanced computer vision algorithms (frame differencing) to detect subtle movements.
- **Live Graph**: Dynamic visualization of movement intensity.
- **Status Alerts**: Immediate visual feedback when movement is detected or the subject is idle.
- **Premium UI**: Glassmorphism design with dark mode and smooth animations.

## Prerequisites

- [Python 3.8+](https://www.python.org/downloads/)
- A webcam connected to your computer.

## Installation

1.  **Clone the repository** (if not already done).
2.  **Create a virtual environment**:
    ```bash
    python -m venv venv
    ```
3.  **Activate the environment**:
    - Windows: `venv\Scripts\activate`
    - Mac/Linux: `source venv/bin/activate`
4.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  **Run the application**:
    ```bash
    python app.py
    ```
2.  **Open your browser**:
    Navigate to [http://127.0.0.1:5000](http://127.0.0.1:5000)
3.  **Monitor**:
    - Ensure your camera is pointed at the baby/subject.
    - The graph will spike when movement occurs.

## Troubleshooting

- **No Video?**: Ensure no other application (Zoom, Teams) is using the camera.
- **False Positives**: Adjust lighting conditions. Shadows can be interpreted as movement.
