from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from config import Config
from database import Database
from monitor_manager import MonitorManager
from snmp_manager import SNMPManager
import atexit
import logging

app = Flask(__name__)
app.config['SECRET_KEY'] = 'latency-monitor-v2-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize components
config = Config()
db = Database()
monitor_manager = MonitorManager(db, config)

# Setup simple logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def on_monitor_data(data):
    """Callback for real-time data."""
    if data:
        socketio.emit('monitor_data', data)
        
        # Check for events
        event_type = None
        message = None
        
        if data.get('type') == 'ping':
            if data.get('packet_loss'):
                event_type = 'packet_loss'
                message = f"Packet loss detected for {data.get('monitor_id')}"
            elif data.get('threshold_exceeded'):
                event_type = 'threshold_exceeded'
                message = f"Latency {data.get('value')}ms exceeded threshold {data.get('threshold')}ms"
                
        if event_type:
            # Log to DB
            db.log_event(
                event_type=event_type,
                latency_ms=data.get('value'),
                threshold_ms=data.get('threshold'),
                destination_ip=str(data.get('monitor_id')), # ID referer
                message=message
            )
            # Emit event for UI logs
            socketio.emit('new_event', {
                'timestamp': data['timestamp'],
                'event_type': event_type,
                'message': message,
                'monitor_id': data.get('monitor_id')
            })

monitor_manager.set_callbacks(on_data=on_monitor_data)

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

# --- API: Device Management ---

@app.route('/api/devices', methods=['GET'])
def get_devices():
    return jsonify(db.get_devices())

@app.route('/api/devices', methods=['POST'])
def add_device():
    data = request.json
    name = data.get('name')
    ip = data.get('ip_address')
    community = data.get('community_string')
    
    if not all([name, ip, community]):
        return jsonify({'error': 'Missing fields'}), 400
        
    try:
        # Validate SNMP
        manager = SNMPManager()
        if not manager.validate_connection(ip, community):
            return jsonify({'error': 'SNMP validation failed. Check IP and Community.'}), 400
            
        device_id = db.add_device(name, ip, community)
        return jsonify({'success': True, 'id': device_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/devices/<int:device_id>', methods=['DELETE'])
def delete_device(device_id):
    try:
        db.delete_device(device_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/devices/<int:device_id>/interfaces', methods=['GET'])
def get_interfaces(device_id):
    # Try getting from DB first
    interfaces = db.get_interfaces(device_id)
    if not interfaces:
        # If empty, try discovery
        device = db.get_device(device_id)
        if not device:
            return jsonify({'error': 'Device not found'}), 404
            
        try:
            manager = SNMPManager()
            discovered = manager.discover_interfaces(device['ip_address'], device['community_string'])
            db.save_interfaces(device_id, discovered)
            interfaces = db.get_interfaces(device_id)
        except Exception as e:
            return jsonify({'error': f"Discovery failed: {str(e)}"}), 500
            
    return jsonify(interfaces)

@app.route('/api/devices/<int:device_id>/discover', methods=['POST'])
def discover_interfaces(device_id):
    """Force discovery."""
    device = db.get_device(device_id)
    if not device:
        return jsonify({'error': 'Device not found'}), 404
        
    try:
        manager = SNMPManager()
        discovered = manager.discover_interfaces(device['ip_address'], device['community_string'])
        db.save_interfaces(device_id, discovered)
        return jsonify({'success': True, 'count': len(discovered)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- API: Monitors (Widgets) ---

@app.route('/api/monitors', methods=['GET'])
def get_monitors():
    return jsonify(db.get_monitors())

@app.route('/api/monitors', methods=['POST'])
def add_monitor():
    data = request.json
    type_ = data.get('type')
    name = data.get('name')
    target = data.get('target')
    settings = data.get('settings', {})
    
    if not all([type_, name, target]):
        return jsonify({'error': 'Missing fields'}), 400
        
    try:
        monitor_id = db.add_monitor(type_, name, target, settings)
        monitor_manager.reload_monitor(monitor_id)
        return jsonify({'success': True, 'id': monitor_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/monitors/<int:monitor_id>', methods=['DELETE'])
def delete_monitor(monitor_id):
    try:
        db.delete_monitor(monitor_id)
        monitor_manager.remove_monitor(monitor_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/events', methods=['GET'])
def get_events():
    limit = request.args.get('limit', 50, type=int)
    return jsonify(db.get_recent_events(limit))

# --- SocketIO ---

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('connection_status', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

# --- Cleanup ---

def cleanup():
    if monitor_manager:
        monitor_manager.stop()

atexit.register(cleanup)

if __name__ == '__main__':
    # Initialize DB (if new)
    # Auto-add default ping monitor if DB is empty?
    # For v2, let's keep it clean or migrate config.json if needed.
    
    # Check if we need to migrate v1 config
    try:
        if not db.get_monitors():
            # Minimal migration of v1 config to a monitor
            legacy_config = config.get_all()
            if legacy_config.get('destination_ip'):
                db.add_monitor(
                    'ping', 
                    'Default Latency', 
                    legacy_config['destination_ip'], 
                    {
                        'threshold': legacy_config.get('latency_threshold_ms', 5), 
                        'interval': legacy_config.get('ping_interval_seconds', 1)
                    }
                )
    except Exception as e:
        print(f"Migration warning: {e}")

    # Start Monitor Loop
    monitor_manager.start()
    
    print("Starting V2 Monitor on http://0.0.0.0:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
