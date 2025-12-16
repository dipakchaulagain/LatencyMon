// WebSocket connection
const socket = io();

// Chart.js instance
let latencyChart = null;

// Data storage
const latencyData = {
    labels: [],
    values: [],
    maxPoints: 60
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function () {
    initializeChart();
    loadConfiguration();
    loadEvents();
    setupEventListeners();
});

// Initialize Chart.js
function initializeChart() {
    const ctx = document.getElementById('latencyChart').getContext('2d');

    latencyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Latency (ms)',
                data: [],
                borderColor: '#4a9eff',
                backgroundColor: 'rgba(74, 158, 255, 0.1)',
                borderWidth: 2,
                tension: 0.4,
                fill: true,
                pointRadius: 2,
                pointHoverRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 0
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: '#2d3748'
                    },
                    ticks: {
                        color: '#9aa0a6',
                        callback: function (value) {
                            return value + ' ms';
                        }
                    }
                },
                x: {
                    grid: {
                        color: '#2d3748'
                    },
                    ticks: {
                        color: '#9aa0a6',
                        maxTicksLimit: 10
                    }
                }
            },
            plugins: {
                legend: {
                    labels: {
                        color: '#e8eaed'
                    }
                },
                tooltip: {
                    backgroundColor: '#1e2433',
                    titleColor: '#e8eaed',
                    bodyColor: '#9aa0a6',
                    borderColor: '#2d3748',
                    borderWidth: 1
                }
            }
        }
    });
}

// Load current configuration
async function loadConfiguration() {
    try {
        const response = await fetch('/api/config');
        const config = await response.json();

        document.getElementById('destinationIp').value = config.destination_ip;
        document.getElementById('thresholdMs').value = config.latency_threshold_ms;
        document.getElementById('intervalSeconds').value = config.ping_interval_seconds;

        document.getElementById('currentDestination').textContent = config.destination_ip;
        document.getElementById('currentThreshold').textContent = config.latency_threshold_ms + ' ms';
    } catch (error) {
        console.error('Error loading configuration:', error);
    }
}

// Load recent events
async function loadEvents() {
    try {
        const response = await fetch('/api/events?limit=50');
        const events = await response.json();

        displayEvents(events);
    } catch (error) {
        console.error('Error loading events:', error);
        document.getElementById('eventsContainer').innerHTML =
            '<div class="no-events">Error loading events</div>';
    }
}

// Display events in the UI
function displayEvents(events) {
    const container = document.getElementById('eventsContainer');

    if (events.length === 0) {
        container.innerHTML = '<div class="no-events">No events recorded yet</div>';
        return;
    }

    container.innerHTML = events.map(event => {
        const timestamp = new Date(event.timestamp).toLocaleString();
        const eventClass = event.event_type === 'packet_loss' ? 'packet-loss' : 'threshold';
        const eventTypeText = event.event_type === 'packet_loss' ? 'Packet Loss' : 'Threshold Exceeded';

        return `
            <div class="event-item ${eventClass}">
                <div class="event-header">
                    <span class="event-type">${eventTypeText}</span>
                    <span class="event-timestamp">${timestamp}</span>
                </div>
                <div class="event-message">${event.message}</div>
            </div>
        `;
    }).join('');
}

// Setup event listeners
function setupEventListeners() {
    // Configuration form
    document.getElementById('configForm').addEventListener('submit', async function (e) {
        e.preventDefault();

        const formData = {
            destination_ip: document.getElementById('destinationIp').value,
            latency_threshold_ms: parseFloat(document.getElementById('thresholdMs').value),
            ping_interval_seconds: parseFloat(document.getElementById('intervalSeconds').value)
        };

        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(formData)
            });

            const result = await response.json();

            if (result.success) {
                alert('Configuration updated successfully!');
                loadConfiguration();
                // Clear chart data on config change
                latencyData.labels = [];
                latencyData.values = [];
                updateChart();
            } else {
                alert('Error: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error updating configuration:', error);
            alert('Error updating configuration');
        }
    });

    // Refresh events button
    document.getElementById('refreshEvents').addEventListener('click', loadEvents);
}

// WebSocket event handlers
socket.on('connect', function () {
    console.log('Connected to server');
    updateConnectionStatus(true);
});

socket.on('disconnect', function () {
    console.log('Disconnected from server');
    updateConnectionStatus(false);
});

socket.on('connection_status', function (data) {
    console.log('Connection status:', data);
});

socket.on('ping_data', function (data) {
    updateLatencyDisplay(data);
    updateChart(data);
});

socket.on('threshold_event', function (event) {
    console.log('Threshold exceeded:', event);
    addEventToUI(event, 'threshold');
});

socket.on('packet_loss_event', function (event) {
    console.log('Packet loss:', event);
    addEventToUI(event, 'packet-loss');
});

// Update connection status indicator
function updateConnectionStatus(connected) {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.querySelector('.status-text');

    if (connected) {
        statusDot.classList.add('connected');
        statusDot.classList.remove('disconnected');
        statusText.textContent = 'Connected';
    } else {
        statusDot.classList.add('disconnected');
        statusDot.classList.remove('connected');
        statusText.textContent = 'Disconnected';
    }
}

// Update latency display
function updateLatencyDisplay(data) {
    const latencyElement = document.getElementById('currentLatency');
    const statusElement = document.getElementById('currentStatus');

    if (data.packet_loss) {
        latencyElement.textContent = 'Packet Loss';
        latencyElement.style.color = '#ef4444';
        statusElement.innerHTML = '<span class="badge badge-danger">Packet Loss</span>';
    } else {
        latencyElement.textContent = data.latency_ms.toFixed(2) + ' ms';

        if (data.threshold_exceeded) {
            latencyElement.style.color = '#fbbf24';
            statusElement.innerHTML = '<span class="badge badge-warning">Threshold Exceeded</span>';
        } else {
            latencyElement.style.color = '#34d399';
            statusElement.innerHTML = '<span class="badge badge-success">Normal</span>';
        }
    }
}

// Update chart with new data
function updateChart(data) {
    if (!data) {
        // Just update the chart with current data
        latencyChart.data.labels = latencyData.labels;
        latencyChart.data.datasets[0].data = latencyData.values;
        latencyChart.update();
        return;
    }

    const timestamp = new Date(data.timestamp).toLocaleTimeString();

    // Add new data point
    latencyData.labels.push(timestamp);

    if (data.packet_loss) {
        // For packet loss, we'll use null to create a gap in the chart
        latencyData.values.push(null);
    } else {
        latencyData.values.push(data.latency_ms);
    }

    // Keep only the last N points
    if (latencyData.labels.length > latencyData.maxPoints) {
        latencyData.labels.shift();
        latencyData.values.shift();
    }

    // Update chart
    latencyChart.data.labels = latencyData.labels;
    latencyChart.data.datasets[0].data = latencyData.values;
    latencyChart.update();
}

// Add event to UI in real-time
function addEventToUI(event, eventClass) {
    const container = document.getElementById('eventsContainer');

    // Remove "no events" message if present
    const noEvents = container.querySelector('.no-events');
    if (noEvents) {
        container.innerHTML = '';
    }

    const timestamp = new Date(event.timestamp).toLocaleString();
    const eventTypeText = eventClass === 'packet-loss' ? 'Packet Loss' : 'Threshold Exceeded';

    const eventHTML = `
        <div class="event-item ${eventClass}">
            <div class="event-header">
                <span class="event-type">${eventTypeText}</span>
                <span class="event-timestamp">${timestamp}</span>
            </div>
            <div class="event-message">${event.message}</div>
        </div>
    `;

    // Add to the top of the list
    container.insertAdjacentHTML('afterbegin', eventHTML);

    // Limit the number of displayed events
    const eventItems = container.querySelectorAll('.event-item');
    if (eventItems.length > 50) {
        eventItems[eventItems.length - 1].remove();
    }
}
