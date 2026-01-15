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
        // Normalize score: Adjusted for higher sensitivity. 
        // We want 500-1000 to show up clearly (10-20%).
        let height = Math.min((score / 5000) * 100, 100);
        bar.style.height = `${height}%`;

        // Color coding - Threshold matches backend (500)
        if (score > 500) {
            bar.style.background = 'var(--success-color)';
            bar.style.boxShadow = '0 0 10px var(--success-color)';
        } else {
            bar.style.background = 'var(--text-secondary)';
            bar.style.boxShadow = 'None';
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
                const videoContainer = document.querySelector('.video-container');

                if (data.motion_detected) {
                    statusText.textContent = "BREATHING DETECTED";
                    statusText.style.color = "var(--success-color)";
                    indicator.style.color = "var(--success-color)";
                    videoOverlayText.textContent = "Live - Active";
                    videoContainer.classList.add('breathing-active');
                } else {
                    statusText.textContent = "IDLE - CHECK BABY";
                    statusText.style.color = "var(--danger-color)"; // More urgent if no breathing
                    indicator.style.color = "var(--danger-color)";
                    videoOverlayText.textContent = "Live - Idle";
                    videoContainer.classList.remove('breathing-active');
                }

                updateGraph(data.motion_score);
            })
            .catch(err => console.error(err));
    }

    // Poll every 100ms
    setInterval(fetchStatus, 100);
});
