from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from config import Config
from database import Database
from ping_monitor import PingMonitor
import atexit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'latency-monitor-secret-key-change-in-production'
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize components
config = Config()
db = Database()
monitor = None

def init_monitor():
    """Initialize the ping monitor with current configuration."""
    global monitor
    
    if monitor and monitor.is_running():
        monitor.stop()
    
    dest_ip = config.get('destination_ip')
    threshold = config.get('latency_threshold_ms')
    interval = config.get('ping_interval_seconds')
    
    monitor = PingMonitor(dest_ip, threshold, interval)
    
    # Register callbacks
    monitor.on_data(on_ping_data)
    monitor.on_threshold_exceeded(on_threshold_exceeded)
    monitor.on_packet_loss(on_packet_loss)
    
    monitor.start()

def on_ping_data(data):
    """Callback for ping data - emit to all connected clients."""
    socketio.emit('ping_data', data)

def on_threshold_exceeded(event):
    """Callback for threshold violations - log and emit."""
    db.log_event(
        event_type='threshold_exceeded',
        latency_ms=event['latency_ms'],
        threshold_ms=event['threshold_ms'],
        destination_ip=event['destination_ip'],
        message=event['message']
    )
    socketio.emit('threshold_event', event)

def on_packet_loss(event):
    """Callback for packet loss - log and emit."""
    db.log_event(
        event_type='packet_loss',
        destination_ip=event['destination_ip'],
        message=event['message']
    )
    socketio.emit('packet_loss_event', event)

@app.route('/')
def index():
    """Serve the main web interface."""
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration."""
    return jsonify(config.get_all())

@app.route('/api/config', methods=['POST'])
def update_config():
    """Update configuration."""
    try:
        data = request.json
        
        # Validate inputs
        if 'destination_ip' in data and not data['destination_ip']:
            return jsonify({'error': 'Destination IP cannot be empty'}), 400
        
        if 'latency_threshold_ms' in data:
            try:
                threshold = float(data['latency_threshold_ms'])
                if threshold <= 0:
                    return jsonify({'error': 'Threshold must be positive'}), 400
            except ValueError:
                return jsonify({'error': 'Invalid threshold value'}), 400
        
        if 'ping_interval_seconds' in data:
            try:
                interval = float(data['ping_interval_seconds'])
                if interval < 0.1:
                    return jsonify({'error': 'Interval must be at least 0.1 seconds'}), 400
            except ValueError:
                return jsonify({'error': 'Invalid interval value'}), 400
        
        # Update configuration
        config.update_config(data)
        
        # Restart monitor with new settings
        init_monitor()
        
        return jsonify({'success': True, 'config': config.get_all()})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/events', methods=['GET'])
def get_events():
    """Get recent events."""
    try:
        limit = request.args.get('limit', 100, type=int)
        events = db.get_recent_events(limit)
        return jsonify(events)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/events/cleanup', methods=['POST'])
def cleanup_events():
    """Cleanup old events."""
    try:
        retention_days = config.get('event_retention_days', 30)
        deleted_count = db.cleanup_old_events(retention_days)
        return jsonify({'success': True, 'deleted_count': deleted_count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get monitoring statistics."""
    try:
        event_count = db.get_event_count()
        return jsonify({
            'total_events': event_count,
            'monitor_running': monitor.is_running() if monitor else False,
            'current_config': config.get_all()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    print('Client connected')
    emit('connection_status', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    print('Client disconnected')

def cleanup():
    """Cleanup on application shutdown."""
    if monitor:
        monitor.stop()

# Register cleanup handler
atexit.register(cleanup)

if __name__ == '__main__':
    # Initialize and start monitor
    init_monitor()
    
    # Run the Flask-SocketIO server
    print("Starting Latency Monitor on http://0.0.0.0:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
