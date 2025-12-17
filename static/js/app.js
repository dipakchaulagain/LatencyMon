const socket = io();
const charts = {}; // Store Chart instances by monitor ID
const chartData = {}; // Store data buffers

document.addEventListener('DOMContentLoaded', () => {
    loadMonitors();
    setupModals();
    setupDeviceManager();
    setInterval(updateClock, 1000);
    updateClock();
});

function updateClock() {
    const clockEl = document.getElementById('liveClock');
    if (clockEl) {
        try {
            const now = new Date();
            const timeString = now.toLocaleTimeString('en-US', { timeZone: 'Asia/Kathmandu' });
            const dateString = now.toLocaleDateString('en-US', { timeZone: 'Asia/Kathmandu' });
            clockEl.textContent = `${dateString} ${timeString}`;
        } catch (e) {
            clockEl.textContent = new Date().toLocaleTimeString();
        }
    }
}

// --- WebSocket ---
socket.on('monitor_data', (data) => {
    updateWidget(data);
});

socket.on('connection_status', (data) => {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.querySelector('.status-text');
    if (data.status === 'connected') {
        statusDot.classList.add('connected');
        statusText.textContent = 'Connected';
    } else {
        statusDot.classList.remove('connected');
        statusText.textContent = 'Disconnected';
    }
});

// --- Dashboard Management ---

async function loadMonitors() {
    try {
        const response = await fetch('/api/monitors');
        const monitors = await response.json();
        const grid = document.getElementById('dashboardGrid');
        grid.innerHTML = '';

        monitors.forEach(monitor => {
            createWidget(monitor);
        });
    } catch (e) {
        console.error("Failed to load monitors", e);
    }
}

function createWidget(monitor) {
    const grid = document.getElementById('dashboardGrid');
    const div = document.createElement('div');
    div.className = 'widget-card';
    div.id = `widget-${monitor.id}`;

    // Stats HTML generation based on type
    let statsHtml = '';
    if (monitor.type === 'ping') {
        statsHtml = `
            <div class="stat-item"><span class="stat-label">Loss:</span><span class="stat-val" id="loss-${monitor.id}">0%</span></div>
            <div class="stat-item"><span class="stat-label">Streak:</span><span class="stat-val" id="streak-${monitor.id}">0</span></div>
            <div class="stat-item"><span class="stat-label">Max:</span><span class="stat-val" id="max-${monitor.id}">-</span></div>
            <div class="stat-item"><span class="stat-label">Avg:</span><span class="stat-val" id="avg-${monitor.id}">-</span></div>
        `;
    } else if (monitor.type === 'bandwidth') {
        statsHtml = `
            <div class="stat-item"><span class="stat-label">In Max:</span><span class="stat-val" id="in-max-${monitor.id}">-</span></div>
            <div class="stat-item"><span class="stat-label">Out Max:</span><span class="stat-val" id="out-max-${monitor.id}">-</span></div>
        `;
    } else if (monitor.type === 'events') {
        statsHtml = `<div class="stat-item">Real-time Logs</div>`;
    }

    div.innerHTML = `
        <div class="widget-header">
            <div class="widget-top-row">
                <div>
                    <div class="widget-title">${monitor.name}</div>
                    <div style="font-size:0.8rem; color:#9aa0a6;">${monitor.type.toUpperCase()}</div>
                </div>
                <div>
                    <span class="widget-value" id="val-${monitor.id}"></span>
                    <span class="delete-widget" onclick="deleteMonitor(${monitor.id})">&times;</span>
                </div>
            </div>
            <div class="widget-stats-row">
                ${statsHtml}
            </div>
        </div>
        <div class="widget-canvas-container" style="${monitor.type === 'events' ? 'overflow-y:auto;' : ''}">
            ${monitor.type === 'events' ?
            `<table class="table" style="font-size:0.8rem; width:100%;">
                    <thead><tr><th>Time</th><th>Event</th><th>Message</th></tr></thead>
                    <tbody id="logs-${monitor.id}"></tbody>
                 </table>`
            : `<canvas id="chart-${monitor.id}"></canvas>`}
        </div>
    `;
    grid.appendChild(div);

    if (monitor.type === 'events') {
        chartData[monitor.id] = { type: 'events', logs: [] };
        // Initial fetch
        fetch('/api/events?limit=20')
            .then(res => res.json())
            .then(events => {
                events.reverse().forEach(evt => addLogEntry(monitor.id, evt));
            });
        return;
    }

    // Initialize Chart
    const ctx = document.getElementById(`chart-${monitor.id}`).getContext('2d');

    // Config based on type
    const isBandwidth = monitor.type === 'bandwidth';
    const datasets = isBandwidth ? [
        { label: 'In (Mbps)', data: [], borderColor: '#34d399', borderWidth: 2, pointRadius: 0 },
        { label: 'Out (Mbps)', data: [], borderColor: '#4a9eff', borderWidth: 2, pointRadius: 0 }
    ] : [
        {
            label: 'Latency (ms)',
            data: [],
            borderColor: '#fbbf24',
            borderWidth: 2,
            fill: true,
            backgroundColor: 'rgba(251, 191, 36, 0.1)',
            pointRadius: 0,
            segment: {
                borderColor: ctx => {
                    // Check if current or next point is above threshold
                    // Passing threshold via closure or getting from settings?
                    // Settings are in 'monitor.settings.threshold'
                    const val = ctx.p0.parsed.y;
                    const nextVal = ctx.p1.parsed.y;
                    const limit = monitor.settings?.threshold || 5;

                    if (val > limit || nextVal > limit) return '#fbbf24'; // Warning color (Yellow)
                    return '#34d399'; // Good color (Green)
                }
            }
        }
    ];

    charts[monitor.id] = new Chart(ctx, {
        type: 'line',
        data: { labels: [], datasets: datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            scales: {
                x: { display: false },
                y: { beginAtZero: true, grid: { color: '#2d3748' } }
            },
            plugins: { legend: { display: isBandwidth } }
        }
    });

    // Initialize data storage with stats tracking
    chartData[monitor.id] = {
        type: monitor.type,
        labels: [],
        values: [],
        pingStats: { total: 0, loss: 0, sum: 0, count: 0, max: 0, streak: 0 },
        bwStats: { maxIn: 0, maxOut: 0 }
    };
}

function addLogEntry(widgetId, event) {
    const tbody = document.getElementById(`logs-${widgetId}`);
    if (!tbody) return;

    const row = document.createElement('tr');
    const time = new Date(event.timestamp).toLocaleTimeString();
    row.innerHTML = `
        <td>${time}</td>
        <td style="color:${event.event_type === 'packet_loss' ? '#ef4444' : '#fbbf24'}">${event.event_type}</td>
        <td>${event.message}</td>
    `;
    tbody.insertBefore(row, tbody.firstChild);

    if (tbody.children.length > 50) tbody.removeChild(tbody.lastChild);
}

// Socket listener for new events
socket.on('new_event', (event) => {
    // Add to all event widgets
    Object.keys(chartData).forEach(id => {
        if (chartData[id].type === 'events') {
            addLogEntry(id, event);
        }
    });
});

function updateWidget(data) {
    const id = data.monitor_id;
    if (!charts[id] && chartData[id]?.type !== 'events') return; // Also check for event widgets

    const chart = charts[id];
    const timestamp = new Date(data.timestamp).toLocaleTimeString();
    const stats = chartData[id];

    // Update value display
    const valEl = document.getElementById(`val-${id}`);

    if (data.type === 'ping') {
        // Update stats
        stats.pingStats.total++;
        if (data.packet_loss) {
            stats.pingStats.loss++;
            stats.pingStats.streak = 0; // Reset streak on loss or count as bad? 
            // Usually streak of threshold is distinct. Let's say Packet Loss ends threshold streak.
        } else {
            stats.pingStats.sum += data.value;
            stats.pingStats.count++;
            if (data.value > stats.pingStats.max) stats.pingStats.max = data.value;

            if (data.threshold_exceeded) {
                stats.pingStats.streak++;
            } else {
                stats.pingStats.streak = 0;
            }
        }

        // Update UI Stats
        const lossPct = ((stats.pingStats.loss / stats.pingStats.total) * 100).toFixed(1);
        const avg = stats.pingStats.count > 0 ? (stats.pingStats.sum / stats.pingStats.count).toFixed(1) : 0;

        document.getElementById(`loss-${id}`).textContent = `${lossPct}%`;
        document.getElementById(`loss-${id}`).className = parseFloat(lossPct) > 0 ? 'stat-val red' : 'stat-val';
        document.getElementById(`max-${id}`).textContent = `${stats.pingStats.max}ms`;
        document.getElementById(`avg-${id}`).textContent = `${avg}ms`;
        const streakEl = document.getElementById(`streak-${id}`);
        if (streakEl) {
            streakEl.textContent = stats.pingStats.streak;
            streakEl.className = stats.pingStats.streak > 0 ? 'stat-val red' : 'stat-val';
        }

        // Main Value
        const val = data.value !== null ? `${data.value} ms` : 'Loss';
        valEl.textContent = val;

        // Color logic
        if (data.packet_loss) {
            valEl.style.color = '#ef4444'; // Red
        } else if (data.threshold_exceeded) {
            valEl.style.color = '#fbbf24'; // Yellow
        } else {
            valEl.style.color = '#34d399'; // Green
        }

        // Update Chart
        const labels = chart.data.labels;
        const mainData = chart.data.datasets[0].data;

        labels.push(timestamp);
        mainData.push(data.value);

        if (labels.length > 60) {
            labels.shift();
            mainData.shift();
        }
    } else if (data.type === 'bandwidth') {
        // Convert bps to Mbps
        const inMbps = parseFloat((data.in_bps / 1000000).toFixed(2));
        const outMbps = parseFloat((data.out_bps / 1000000).toFixed(2));

        // Update Stats
        if (inMbps > stats.bwStats.maxIn) stats.bwStats.maxIn = inMbps;
        if (outMbps > stats.bwStats.maxOut) stats.bwStats.maxOut = outMbps;

        // Update UI Stats
        document.getElementById(`in-max-${id}`).textContent = `${stats.bwStats.maxIn} Mbps`;
        document.getElementById(`out-max-${id}`).textContent = `${stats.bwStats.maxOut} Mbps`;

        // Main Value
        valEl.textContent = `↓${inMbps} ↑${outMbps} Mbps`;
        valEl.style.color = '#34d399';

        const labels = chart.data.labels;
        labels.push(timestamp);
        chart.data.datasets[0].data.push(inMbps);
        chart.data.datasets[1].data.push(outMbps);

        if (labels.length > 60) {
            labels.shift();
            chart.data.datasets[0].data.shift();
            chart.data.datasets[1].data.shift();
        }
    }

    chart.update();
}

async function deleteMonitor(id) {
    if (!confirm('Delete this monitor?')) return;
    try {
        await fetch(`/api/monitors/${id}`, { method: 'DELETE' });
        document.getElementById(`widget-${id}`).remove();
        delete charts[id];
    } catch (e) {
        alert('Error deleting monitor');
    }
}

// --- Modals & Forms ---

function setupModals() {
    const modal = document.getElementById('addWidgetModal');
    const btn = document.getElementById('addWidgetBtn');
    const close = document.getElementById('cancelAddWidget');
    const save = document.getElementById('saveWidget');

    btn.onclick = () => modal.classList.remove('hidden');
    close.onclick = () => modal.classList.add('hidden');

    // Type change handler
    const typeSelect = document.getElementById('monitorType');
    const pingGroup = document.getElementById('pingTargetGroup');
    const bwGroup = document.getElementById('bandwidthTargetGroup');
    const thresholdGroup = document.getElementById('pingThresholdGroup');

    typeSelect.onchange = () => {
        // Reset
        pingGroup.classList.add('hidden');
        bwGroup.classList.add('hidden');
        thresholdGroup.classList.add('hidden');

        if (typeSelect.value === 'ping') {
            pingGroup.classList.remove('hidden');
            thresholdGroup.classList.remove('hidden');
        } else if (typeSelect.value === 'bandwidth') {
            bwGroup.classList.remove('hidden');
            loadDevicesForSelect();
        } else if (typeSelect.value === 'events') {
            // No extra settings needed for now
        }
    };

    save.onclick = async () => {
        const type = typeSelect.value;
        const name = document.getElementById('monitorName').value;
        const interval = document.getElementById('monitorInterval').value;
        let target, settings = { interval: parseFloat(interval) };

        if (!name) return alert('Name Required');

        if (type === 'ping') {
            target = document.getElementById('targetIP').value;
            const threshold = document.getElementById('monitorThreshold').value;
            if (!target) return alert('Target IP Required');
            settings.threshold = parseFloat(threshold);
        } else if (type === 'bandwidth') {
            target = document.getElementById('interfaceSelect').value;
            if (!target) return alert('Interface Required');
        } else if (type === 'events') {
            target = "Global Events"; // Dummy target for backend validation
        }

        try {
            const res = await fetch('/api/monitors', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type, name, target, settings })
            });
            if (res.ok) {
                modal.classList.add('hidden');
                loadMonitors();
            } else {
                alert('Failed to add monitor');
            }
        } catch (e) {
            alert('Error: ' + e);
        }
    };
}

async function loadDevicesForSelect() {
    const select = document.getElementById('deviceSelect');
    select.innerHTML = '<option value="">Loading...</option>';
    try {
        const res = await fetch('/api/devices');
        const devices = await res.json();
        select.innerHTML = '<option value="">Select a device...</option>';
        devices.forEach(d => {
            select.innerHTML += `<option value="${d.id}">${d.name} (${d.ip_address})</option>`;
        });

        select.onchange = loadInterfacesForSelect;
    } catch (e) {
        select.innerHTML = '<option>Error loading</option>';
    }
}

async function loadInterfacesForSelect() {
    const deviceId = document.getElementById('deviceSelect').value;
    const ifSelect = document.getElementById('interfaceSelect');
    ifSelect.disabled = true;
    ifSelect.innerHTML = '<option>Loading...</option>';

    if (!deviceId) return;

    try {
        const res = await fetch(`/api/devices/${deviceId}/interfaces`);
        const interfaces = await res.json();
        ifSelect.innerHTML = '<option value="">Select interface...</option>';
        interfaces.forEach(i => {
            ifSelect.innerHTML += `<option value="${i.id}">${i.name} (idx: ${i.if_index})</option>`;
        });
        ifSelect.disabled = false;
    } catch (e) {
        ifSelect.innerHTML = '<option>Error loading interfaces</option>';
    }
}

// --- Device Manager ---

function setupDeviceManager() {
    const modal = document.getElementById('deviceManagerModal');
    const openBtn = document.getElementById('openDeviceManager');
    const closeBtn = document.getElementById('closeDeviceManager');
    const addBtn = document.getElementById('addDeviceBtn');

    openBtn.onclick = () => {
        modal.classList.remove('hidden');
        loadDevicesList();
    };
    closeBtn.onclick = () => modal.classList.add('hidden');

    addBtn.onclick = async () => {
        const name = document.getElementById('newDeviceName').value;
        const ip = document.getElementById('newDeviceIP').value;
        const community = document.getElementById('newDeviceCommunity').value;

        if (!name || !ip || !community) return alert('All fields required');

        addBtn.innerText = 'Validating...';
        try {
            const res = await fetch('/api/devices', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name, ip_address: ip, community_string: community })
            });

            const data = await res.json();
            if (res.ok) {
                alert('Device Added');
                loadDevicesList();
                // clear inputs
                document.getElementById('newDeviceName').value = '';
                document.getElementById('newDeviceIP').value = '';
            } else {
                alert('Error: ' + data.error);
            }
        } catch (e) {
            alert('Request Failed');
        } finally {
            addBtn.innerText = 'Add Device';
        }
    };
}

async function loadDevicesList() {
    const list = document.getElementById('devicesList');
    list.innerHTML = 'Loading...';
    try {
        const res = await fetch('/api/devices');
        const devices = await res.json();
        list.innerHTML = '';
        if (devices.length === 0) list.innerHTML = '<div style="padding:10px;text-align:center;">No devices found</div>';

        devices.forEach(d => {
            const div = document.createElement('div');
            div.className = 'device-item';
            div.innerHTML = `
                <div class="device-info">
                    <span class="device-name">${d.name}</span>
                    <span class="device-ip">${d.ip_address} | ${d.community_string}</span>
                </div>
                <button class="btn btn-small btn-secondary" onclick="deleteDevice(${d.id})">Delete</button>
            `;
            list.appendChild(div);
        });
    } catch (e) {
        list.innerText = 'Error loading devices';
    }
}

async function deleteDevice(id) {
    if (!confirm('Delete device and all its monitors?')) return;
    await fetch(`/api/devices/${id}`, { method: 'DELETE' });
    loadDevicesList();
}
