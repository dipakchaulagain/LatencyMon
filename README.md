# Latency Monitor

A lightweight web-based latency monitoring tool designed for resource-constrained VMs. Continuously monitors network latency via ICMP ping, displays real-time graphs, and logs threshold violations and packet loss events.

## Features

- 🌐 **Continuous Ping Monitoring**: Real-time latency tracking to any destination IP
- 📊 **Live Graphing**: Interactive Chart.js graph showing the last 60 seconds of data
- ⚠️ **Threshold Detection**: Automatic detection and logging when latency exceeds configurable threshold
- 📉 **Packet Loss Detection**: Identifies and logs packet loss events with a dedicated counter
- 📱 **Responsive Design**: Optimized UI for mobile and desktop screens with collapsible panels
- ⚙️ **Configurable**: Easy web-based configuration for destination IP, threshold, and ping interval
- 💾 **Event Logging**: SQLite database stores all threshold violations and packet loss events
- 🔄 **Auto-Start**: Systemd service for automatic startup and restart on failure

## System Requirements

- **OS**: Linux (Ubuntu, Debian, CentOS, etc.)
- **CPU**: 1 core minimum
- **RAM**: 2GB maximum (typically uses <100MB)
- **Storage**: 10GB (application uses <50MB)
- **Python**: 3.7 or higher
- **Network**: Outbound ICMP (ping) access

## Quick Start with Docker (Recommended)

The easiest way to deploy the application is using Docker:

```bash
# Build and start the container
docker compose build
docker compose up -d

# Check status
docker compose logs

# Access the application at http://localhost:5000
```

**Database**: The SQLite database will be automatically created in the `./data/` directory on first run and persists across container restarts.

**Stopping**: 
```bash
docker compose down
```

## Installation

### 1. Clone or Copy Files

```bash
# Create application directory
sudo mkdir -p /opt/latency-monitor
cd /opt/latency-monitor

# Copy all application files to this directory
```

### 2. Install Python Dependencies

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Application

Edit `config.json` to set your preferences:

```json
{
    "destination_ip": "8.8.8.8",
    "latency_threshold_ms": 5,
    "ping_interval_seconds": 1,
    "max_graph_points": 60,
    "event_retention_days": 30
}
```

### 4. Test the Application

```bash
# Run the application manually
python app.py
```

Open your browser and navigate to `http://your-vm-ip:5000`

### 5. Setup Systemd Service (Optional but Recommended)

```bash
# Create user for the service
sudo useradd -r -s /bin/false latency-monitor

# Set ownership
sudo chown -R latency-monitor:latency-monitor /opt/latency-monitor

# Copy service file
sudo cp latency-monitor.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable latency-monitor

# Start the service
sudo systemctl start latency-monitor

# Check status
sudo systemctl status latency-monitor
```

## Usage

### Web Interface

Access the web interface at `http://your-vm-ip:5000`

The interface provides:

1. **Current Status**: Real-time display of current latency, destination IP, threshold, and packet drops.
2. **Configuration Panel**: Toggle using the ⚙️ icon to update settings.
3. **Latency Graph**: Live graph showing the last 60 seconds of latency data.
4. **Events Log**: List of all threshold violations and packet loss events.

### Configuration

You can update the configuration in two ways:

1. **Web Interface**: Use the collapsible configuration form on the main page.
2. **Config File**: Edit `config.json` and restart the service.

### API Endpoints

- `GET /api/config` - Get current configuration
- `POST /api/config` - Update configuration
- `GET /api/events?limit=100` - Get recent events
- `GET /api/stats` - Get monitoring statistics

## Running on Windows (Development)

For development on Windows:

```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

**Note**: The `ping3` library requires administrator privileges on Windows. Run your terminal as Administrator.

## Troubleshooting

### Permission Issues

If you get permission errors when running ping:

```bash
# Grant ping capabilities to Python
sudo setcap cap_net_raw+ep $(readlink -f $(which python3))
```

Or run the application as root (not recommended for production):

```bash
sudo python app.py
```

### Service Not Starting

Check the service logs:

```bash
sudo journalctl -u latency-monitor -f
```

### High CPU Usage

If CPU usage is high, increase the ping interval:

```json
{
    "ping_interval_seconds": 2
}
```

### Database Growing Too Large

The application automatically cleans up events older than the retention period. You can manually trigger cleanup:

```bash
curl -X POST http://localhost:5000/api/events/cleanup
```

## Architecture

- **Backend**: Python Flask with Flask-SocketIO for real-time communication
- **Frontend**: Vanilla JavaScript with Chart.js for graphing
- **Database**: SQLite for event storage
- **Ping**: `ping3` library for ICMP ping functionality
- **Communication**: WebSocket for real-time updates

## Resource Usage

Typical resource usage on a 1 core, 2GB RAM VM:

- **CPU**: 2-5% (with 1-second ping interval)
- **RAM**: 50-80MB
- **Storage**: <50MB (application + database)
- **Network**: Minimal (ICMP packets only)

## Security Considerations

- The application runs on port 5000 by default (no authentication)
- For production, consider:
  - Running behind a reverse proxy (nginx/Apache)
  - Adding authentication
  - Using HTTPS
  - Restricting access via firewall rules

## License

This project is provided as-is for monitoring purposes.

> [!NOTE]
> This product is built with [Vibecode](https://vibecode.ai).
