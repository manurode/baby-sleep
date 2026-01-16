document.addEventListener('DOMContentLoaded', () => {
    const statusText = document.getElementById('status-text');
    const scoreValue = document.getElementById('score-value');
    const indicator = document.querySelector('.indicator-dot');
    const videoOverlayText = document.querySelector('.video-overlay span');
    const graphContainer = document.getElementById('motion-graph');
    const body = document.body;
    const monitorCard = document.querySelector('.monitor-card');
    const startOverlay = document.getElementById('start-overlay');
    const startBtn = document.getElementById('start-btn');

    // ROI Elements
    const roiOverlay = document.getElementById('roi-overlay');
    const selectionBox = document.getElementById('selection-box');
    const resetRoiBtn = document.getElementById('reset-roi-btn');

    // Configuration
    const THRESHOLD = 500;
    const POLLING_RATE = 200; // ms (Poll less frequently for performance)
    const ALARM_TIMEOUT = 10000; // 10 seconds of no movement
    const GRAPH_HISTORY_LIMIT = 200; // Keep 200 bars in DOM

    // State
    let lastMovementTime = Date.now();
    let isAlarmActive = false;

    // ROI State
    let isDrawingRoi = false;
    let roiStartX = 0;
    let roiStartY = 0;
    let hasActiveRoi = false;

    // Audio Alarm Logic
    let audioCtx = null;
    let alarmTimer = null;

    function initAudio() {
        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (audioCtx.state === 'suspended') {
            audioCtx.resume();
        }
    }
    // Removed automatic click listener in favor of explicit start button
    // document.addEventListener('click', initAudio, { once: true });

    function playBeep() {
        if (!audioCtx) initAudio();
        if (!audioCtx || audioCtx.state === 'suspended') return;

        const oscillator = audioCtx.createOscillator();
        const gainNode = audioCtx.createGain();

        oscillator.connect(gainNode);
        gainNode.connect(audioCtx.destination);

        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(880, audioCtx.currentTime); // A5
        gainNode.gain.setValueAtTime(0.1, audioCtx.currentTime);

        oscillator.start();
        oscillator.stop(audioCtx.currentTime + 0.3);
    }

    function startAlarmSound() {
        if (alarmTimer) return;
        playBeep();
        alarmTimer = setInterval(playBeep, 1000);
    }

    function stopAlarmSound() {
        if (alarmTimer) {
            clearInterval(alarmTimer);
            alarmTimer = null;
        }
    }

    function activateAlarm() {
        if (isAlarmActive) return;
        isAlarmActive = true;

        statusText.textContent = "ALARM: NO MOVEMENT DETECTED!";
        statusText.style.color = "var(--danger-color)";
        videoOverlayText.textContent = "ALARM - CHECK BABY";
        videoOverlayText.style.color = "var(--danger-color)";

        indicator.classList.remove('active');
        indicator.classList.add('alarm');

        body.classList.add('alarm-active');
        monitorCard.classList.add('alarm-state');
        startAlarmSound();
    }

    function deactivateAlarm() {
        if (!isAlarmActive) return;
        isAlarmActive = false;

        // Reset styles (Text will be updated by regular update loop)
        indicator.classList.remove('alarm');
        body.classList.remove('alarm-active');
        monitorCard.classList.remove('alarm-state');
        stopAlarmSound();
    }

    function updateGraph(score, detected) {
        const bar = document.createElement('div');
        bar.className = 'bar';

        // Normalize height (logarithmic scale might be better, but linear for now)
        // Cap at 100%
        let height = Math.min((score / 5000) * 100, 100);
        // Ensure some visibility even for low scores if detected
        if (height < 5 && score > 0) height = 5;

        bar.style.height = `${height}%`;

        if (isAlarmActive) {
            bar.classList.add('alarm');
        } else if (detected) {
            bar.classList.add('active');
        }

        // Prepend to graph (since we use direction: rtl for "scrolling back")
        // Or append? With RTL, the "start" is the right side.
        // If we appendChild, it goes to the "left" visually if flex-direction is row-reverse
        // But with default flex and direction: rtl:
        // First child is on the RIGHT.
        // So we should prepend new bars so they appear on the right?
        // Actually, let's keep it simple: Append child, scroll to end.
        // CSS direction: rtl handling:
        // In `direction: rtl`, the first item is on the right.
        // So if we Prepend, the new item appears on the right (start of container).

        graphContainer.prepend(bar);

        // Prune old bars
        if (graphContainer.children.length > GRAPH_HISTORY_LIMIT) {
            graphContainer.removeChild(graphContainer.lastChild);
        }
    }

    function fetchStatus() {
        fetch('/status')
            .then(response => response.json())
            .then(data => {
                const now = Date.now();
                const score = data.motion_score;
                const detected = data.motion_detected || score > THRESHOLD;

                // Update Values
                scoreValue.textContent = Math.round(score).toLocaleString();

                // Logic
                if (detected) {
                    lastMovementTime = now;
                    deactivateAlarm(); // Recovery

                    statusText.textContent = "Breathing Active";
                    statusText.style.color = "var(--success-color)";
                    videoOverlayText.textContent = "Live - Active";
                    videoOverlayText.style.color = "var(--success-color)";

                    indicator.classList.add('active');
                } else {
                    indicator.classList.remove('active');

                    // Check Alarm
                    if (now - lastMovementTime > ALARM_TIMEOUT) {
                        activateAlarm();
                    } else {
                        // Warning phase
                        statusText.textContent = `No movement for ${Math.round((now - lastMovementTime) / 1000)}s`;
                        statusText.style.color = "var(--text-secondary)";
                        videoOverlayText.textContent = "Live - Idle";
                        videoOverlayText.style.color = "var(--text-secondary)";
                    }
                }

                updateGraph(score, detected);
            })
            .catch(err => {
                console.error("Connection lost", err);
                statusText.textContent = "CONNECTION LOST";
                statusText.style.color = "var(--danger-color)";
            });
    }

    // Start Logic
    function startMonitor() {
        initAudio();
        startOverlay.classList.add('hidden');

        // Start polling loop
        fetchStatus();
        setInterval(fetchStatus, POLLING_RATE);
    }

    startBtn.addEventListener('click', startMonitor);

    // --- ROI Selection Logic ---
    function sendRoiToServer(x, y, w, h) {
        fetch('/set_roi', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ x, y, w, h })
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') {
                    hasActiveRoi = true;
                    resetRoiBtn.classList.add('visible');
                    console.log('ROI set:', data.roi);
                }
            })
            .catch(err => console.error('Failed to set ROI:', err));
    }

    function resetRoi() {
        fetch('/reset_roi', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') {
                    hasActiveRoi = false;
                    resetRoiBtn.classList.remove('visible');
                    console.log('ROI cleared.');
                }
            })
            .catch(err => console.error('Failed to reset ROI:', err));
    }

    roiOverlay.addEventListener('mousedown', (e) => {
        const rect = roiOverlay.getBoundingClientRect();
        roiStartX = e.clientX - rect.left;
        roiStartY = e.clientY - rect.top;
        isDrawingRoi = true;
        selectionBox.style.left = `${roiStartX}px`;
        selectionBox.style.top = `${roiStartY}px`;
        selectionBox.style.width = '0';
        selectionBox.style.height = '0';
        selectionBox.classList.add('active');
    });

    roiOverlay.addEventListener('mousemove', (e) => {
        if (!isDrawingRoi) return;
        const rect = roiOverlay.getBoundingClientRect();
        const currentX = e.clientX - rect.left;
        const currentY = e.clientY - rect.top;

        const left = Math.min(roiStartX, currentX);
        const top = Math.min(roiStartY, currentY);
        const width = Math.abs(currentX - roiStartX);
        const height = Math.abs(currentY - roiStartY);

        selectionBox.style.left = `${left}px`;
        selectionBox.style.top = `${top}px`;
        selectionBox.style.width = `${width}px`;
        selectionBox.style.height = `${height}px`;
    });

    roiOverlay.addEventListener('mouseup', (e) => {
        if (!isDrawingRoi) return;
        isDrawingRoi = false;
        selectionBox.classList.remove('active');

        const rect = roiOverlay.getBoundingClientRect();
        const currentX = e.clientX - rect.left;
        const currentY = e.clientY - rect.top;

        const left = Math.min(roiStartX, currentX);
        const top = Math.min(roiStartY, currentY);
        const width = Math.abs(currentX - roiStartX);
        const height = Math.abs(currentY - roiStartY);

        // Calculate normalized coordinates (0-1)
        const normX = left / rect.width;
        const normY = top / rect.height;
        const normW = width / rect.width;
        const normH = height / rect.height;

        // Minimum size check to avoid accidental clicks
        if (normW > 0.02 && normH > 0.02) {
            sendRoiToServer(normX, normY, normW, normH);
        }
    });

    // Handle mouse leaving the overlay while drawing
    roiOverlay.addEventListener('mouseleave', () => {
        if (isDrawingRoi) {
            isDrawingRoi = false;
            selectionBox.classList.remove('active');
        }
    });

    resetRoiBtn.addEventListener('click', resetRoi);
});
