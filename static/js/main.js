document.addEventListener('DOMContentLoaded', () => {
    const statusText = document.getElementById('status-text');
    const scoreValue = document.getElementById('score-value');
    const indicator = document.querySelector('.indicator-dot');
    const videoOverlayText = document.querySelector('.video-overlay span');
    const graphContainer = document.getElementById('motion-graph');
    const body = document.body;
    const monitorCard = document.querySelector('.monitor-card');

    // Configuration
    const THRESHOLD = 500;
    const POLLING_RATE = 200; // ms (Poll less frequently for performance)
    const ALARM_TIMEOUT = 10000; // 10 seconds of no movement
    const GRAPH_HISTORY_LIMIT = 200; // Keep 200 bars in DOM

    // State
    let lastMovementTime = Date.now();
    let isAlarmActive = false;

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
    }

    function deactivateAlarm() {
        if (!isAlarmActive) return;
        isAlarmActive = false;

        // Reset styles (Text will be updated by regular update loop)
        indicator.classList.remove('alarm');
        body.classList.remove('alarm-active');
        monitorCard.classList.remove('alarm-state');
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

    // Start Loop
    setInterval(fetchStatus, POLLING_RATE);
});
