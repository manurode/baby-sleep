document.addEventListener('DOMContentLoaded', () => {
    const statusText = document.getElementById('status-text');
    const scoreValue = document.getElementById('score-value');
    const indicator = document.querySelector('.indicator-dot');
    const videoOverlayText = document.querySelector('.video-overlay span');
    const graphContainer = document.getElementById('motion-graph');

    // Graph limits
    const maxBars = 50;

    function updateGraph(score) {
        const bar = document.createElement('div');
        bar.className = 'bar';
        // Normalize score roughly (assuming 0-10000 range usually)
        let height = Math.min((score / 15000) * 100, 100);
        bar.style.height = `${height}%`;

        // Color coding
        if (score > 5000) {
            bar.style.backgroundColor = 'var(--success-color)';
        } else {
            bar.style.backgroundColor = 'var(--text-secondary)';
        }

        graphContainer.appendChild(bar);

        if (graphContainer.children.length > maxBars) {
            graphContainer.removeChild(graphContainer.firstChild);
        }
    }

    function fetchStatus() {
        fetch('/status')
            .then(response => response.json())
            .then(data => {
                // Update text
                scoreValue.textContent = Math.round(data.motion_score).toLocaleString();

                if (data.motion_detected) {
                    statusText.textContent = "DETECTED";
                    statusText.style.color = "var(--success-color)";
                    indicator.style.color = "var(--success-color)";
                    videoOverlayText.textContent = "Live - Movement";
                } else {
                    statusText.textContent = "IDLE";
                    statusText.style.color = "var(--text-secondary)";
                    indicator.style.color = "var(--danger-color)";
                    videoOverlayText.textContent = "Live - Idle";
                }

                updateGraph(data.motion_score);
            })
            .catch(err => console.error(err));
    }

    // Poll every 100ms
    setInterval(fetchStatus, 100);
});
