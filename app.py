from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from config import Config
from database import Database
from monitor_manager import MonitorManager
from snmp_manager import SNMPManager
from datetime import datetime
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
        
        # Log metric
        try:
            val = None
            if data['type'] == 'ping':
                val = data.get('value')
            elif data['type'] == 'bandwidth':
                val = {'in': data.get('in_bps',0), 'out': data.get('out_bps',0)}
            
            if val is not None:
                 db.log_metric(
                     data['monitor_id'],
                     data.get('monitor_name', 'Unknown'),
                     data['type'],
                     data['timestamp'],
                     val
                 )
        except Exception as e:
            logging.error(f"Metric Log Error: {e}")

        # Check for events
        event_type = None
        message = None
        
        if data.get('type') == 'ping':
            if data.get('packet_loss'):
                event_type = 'packet_loss'
                message = f"[{data.get('monitor_name', 'Unknown')}] Packet loss detected"
            elif data.get('threshold_exceeded'):
                event_type = 'threshold_exceeded'
                message = f"[{data.get('monitor_name', 'Unknown')}] Latency {data.get('value')}ms exceeded threshold {data.get('threshold')}ms"
        
        elif data.get('type') == 'bandwidth':
             if data.get('threshold_exceeded'):
                 event_type = 'threshold_exceeded'
                 in_mbps = round(data.get('in_bps', 0) / 1e6, 2)
                 out_mbps = round(data.get('out_bps', 0) / 1e6, 2)
                 message = f"[{data.get('monitor_name', 'Unknown')}] Bandwidth exceeded {data.get('threshold')}Mbps (In: {in_mbps}, Out: {out_mbps})"
                
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

@app.route('/api/report', methods=['GET'])
def generate_report():
    hours = request.args.get('hours', 24, type=int)
    from fpdf import FPDF
    import tempfile
    import os
    import json
    import matplotlib
    matplotlib.use('Agg') # Non-GUI backend
    import matplotlib.pyplot as plt
    from flask import send_file

    events = db.get_events_range(hours)
    metrics = db.get_metrics_range(hours)
    
    # Process Metrics
    monitors_data = {}
    for m in metrics:
        mid = m['monitor_id']
        if mid not in monitors_data:
            monitors_data[mid] = {'name': m['monitor_name'], 'type': m['type'], 'ts': [], 'val': []}
        monitors_data[mid]['ts'].append(datetime.fromisoformat(m['timestamp']))
        try:
            val = json.loads(m['value_json'])
            monitors_data[mid]['val'].append(val)
        except:
            monitors_data[mid]['val'].append(None)

    # Generate Plots
    plot_files = []
    
    def generate_plot(mid, data):
        try:
            fig, ax = plt.subplots(figsize=(10, 4))
            dates = data['ts']
            
            if data['type'] == 'ping':
                # Filter None (Loss)
                y_clean = [v if v is not None else 0 for v in data['val']]
                # Plot
                ax.plot(dates, y_clean, label='Latency (ms)', color='#3b82f6')
                ax.set_title(f"Ping: {data['name']}")
                ax.set_ylabel('ms')
            elif data['type'] == 'bandwidth':
                vis = [v['in']/1e6 for v in data['val']]
                vos = [v['out']/1e6 for v in data['val']]
                ax.plot(dates, vis, label='In (Mbps)', color='#10b981')
                ax.plot(dates, vos, label='Out (Mbps)', color='#6366f1')
                ax.set_title(f"Bandwidth: {data['name']}")
                ax.set_ylabel('Mbps')
            
            ax.legend()
            ax.grid(True, alpha=0.3)
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            fig.savefig(path)
            plt.close(fig)
            plot_files.append(path)
            return path
        except Exception as e:
            logging.error(f"Plot Error: {e}")
            return None

    # Simple PDF generation
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 15)
            self.cell(0, 10, f'Latency Monitor Report - Last {hours} Hours', 0, 1, 'C')
            self.ln(10)

        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    # Summary
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Summary (Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})", 0, 1)
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 7, f"Total Events: {len(events)}", 0, 1)
    
    pkts_loss = sum(1 for e in events if e['event_type'] == 'packet_loss')
    threshold = sum(1 for e in events if e['event_type'] == 'threshold_exceeded')
    
    pdf.cell(0, 7, f"Packet Loss Events: {pkts_loss}", 0, 1)
    pdf.cell(0, 7, f"Threshold Violations: {threshold}", 0, 1)
    pdf.ln(10)
    
    # Graphs
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Performance Graphs", 0, 1)
    pdf.ln(5)
    
    for mid, mdata in monitors_data.items():
        if not mdata['ts']: continue
        img_path = generate_plot(mid, mdata)
        if img_path:
            pdf.set_font("Arial", 'B', 11)
            pdf.cell(0, 10, f"{mdata['name']} ({mdata['type'].upper()})", 0, 1)
            pdf.image(img_path, x=10, w=190)
            pdf.ln(5)
            
    # Event Log Table
    pdf.add_page()
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 10, "Event Log", 0, 1)
    
    pdf.set_font("Arial", 'B', 9)
    # Header
    pdf.cell(40, 7, "Timestamp", 1)
    pdf.cell(30, 7, "Type", 1)
    pdf.cell(120, 7, "Message", 1)
    pdf.ln()
    
    pdf.set_font("Arial", size=8)
    for event in events:
        ts = event['timestamp'].replace('T', ' ')[:19]
        pdf.cell(40, 7, ts, 1)
        pdf.cell(30, 7, event['event_type'], 1)
        pdf.cell(120, 7, str(event['message'])[:90], 1) # Scan/Truncate
        pdf.ln()

    # Save to temp
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    pdf.output(path)
    
    # Cleanup
    for p in plot_files:
        if os.path.exists(p): os.remove(p)
    
    cleanup_func = lambda: os.remove(path) if os.path.exists(path) else None
    
    # Send file
    try:
        return send_file(path, as_attachment=True, download_name=f"report_{hours}h.pdf")
    except Exception as e:
        cleanup_func()
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
