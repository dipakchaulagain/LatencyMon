import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any
import threading
import json
import os

class Database:
    """SQLite database management for monitoring tool v2."""
    
    def __init__(self, db_file: str = None):
        # Use environment variable if set, otherwise use default
        if db_file is None:
            db_file = os.environ.get('DATABASE_URL', 'latency_monitor.db')
        
        self.db_file = db_file
        
        # Ensure parent directory exists
        db_dir = os.path.dirname(self.db_file)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        self.lock = threading.Lock()
        self.init_database()
    
    def get_connection(self):
        """Get a database connection."""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Initialize database schema."""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Events table (v1 compatible)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    latency_ms REAL,
                    threshold_ms REAL,
                    destination_ip TEXT NOT NULL,
                    message TEXT
                )
            ''')

            # Metrics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    monitor_id INTEGER,
                    monitor_name TEXT,
                    type TEXT,
                    timestamp TEXT,
                    value_json TEXT
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(timestamp)')
            
            # Devices table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    community_string TEXT NOT NULL,
                    snmp_version INTEGER DEFAULT 2,
                    created_at TEXT NOT NULL
                )
            ''')
            
            # Interfaces table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS interfaces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    if_index INTEGER NOT NULL,
                    description TEXT,
                    speed INTEGER,
                    FOREIGN KEY (device_id) REFERENCES devices (id)
                )
            ''')
            
            # Monitors table (Widget configurations)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS monitors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL, -- 'ping', 'bandwidth'
                    name TEXT NOT NULL,
                    target TEXT NOT NULL, -- IP or interface_id
                    settings TEXT NOT NULL, -- JSON string
                    created_at TEXT NOT NULL
                )
            ''')
            
            # Indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON events(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_device_id ON interfaces(device_id)')
            
            conn.commit()
            conn.close()

    # --- Device Management ---
    
    def add_device(self, name: str, ip_address: str, community: str) -> int:
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO devices (name, ip_address, community_string, created_at)
                VALUES (?, ?, ?, ?)
            ''', (name, ip_address, community, datetime.now().isoformat()))
            device_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return device_id

    def get_devices(self) -> List[Dict]:
        with self.lock:
            conn = self.get_connection()
            rows = conn.execute('SELECT * FROM devices').fetchall()
            conn.close()
            return [dict(row) for row in rows]
            
    def get_device(self, device_id: int) -> Dict:
        with self.lock:
            conn = self.get_connection()
            row = conn.execute('SELECT * FROM devices WHERE id = ?', (device_id,)).fetchone()
            conn.close()
            return dict(row) if row else None
            
    def delete_device(self, device_id: int):
        with self.lock:
            conn = self.get_connection()
            conn.execute('DELETE FROM interfaces WHERE device_id = ?', (device_id,))
            conn.execute('DELETE FROM devices WHERE id = ?', (device_id,))
            conn.commit()
            conn.close()

    # --- Interface Management ---

    def save_interfaces(self, device_id: int, interfaces: List[Dict]):
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # clear existing interfaces for this device to avoid duplicates/stale data
            cursor.execute('DELETE FROM interfaces WHERE device_id = ?', (device_id,))
            
            for iface in interfaces:
                cursor.execute('''
                    INSERT INTO interfaces (device_id, name, if_index, description, speed)
                    VALUES (?, ?, ?, ?, ?)
                ''', (device_id, iface['name'], iface['index'], iface.get('description', ''), iface.get('speed', 0)))
            
            conn.commit()
            conn.close()
            
    def get_interfaces(self, device_id: int) -> List[Dict]:
        with self.lock:
            conn = self.get_connection()
            rows = conn.execute('SELECT * FROM interfaces WHERE device_id = ?', (device_id,)).fetchall()
            conn.close()
            return [dict(row) for row in rows]

    def get_interface(self, interface_id: int) -> Dict:
        with self.lock:
            conn = self.get_connection()
            row = conn.execute('SELECT * FROM interfaces WHERE id = ?', (interface_id,)).fetchone()
            conn.close()
            return dict(row) if row else None

    # --- Monitor Management ---

    def add_monitor(self, type_: str, name: str, target: str, settings: Dict) -> int:
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO monitors (type, name, target, settings, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (type_, name, target, json.dumps(settings), datetime.now().isoformat()))
            monitor_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return monitor_id

    def get_monitors(self) -> List[Dict]:
        with self.lock:
            conn = self.get_connection()
            rows = conn.execute('SELECT * FROM monitors').fetchall()
            conn.close()
            result = []
            for row in rows:
                item = dict(row)
                item['settings'] = json.loads(item['settings'])
                result.append(item)
            return result

    def get_monitor(self, monitor_id: int) -> Dict:
        with self.lock:
            conn = self.get_connection()
            row = conn.execute('SELECT * FROM monitors WHERE id = ?', (monitor_id,)).fetchone()
            conn.close()
            if row:
                item = dict(row)
                item['settings'] = json.loads(item['settings'])
                return item
            return None

    def delete_monitor(self, monitor_id: int):
        with self.lock:
            conn = self.get_connection()
            conn.execute('DELETE FROM monitors WHERE id = ?', (monitor_id,))
            conn.commit()
            conn.close()

    # --- Events (Legacy support + New) ---
    
    def log_event(self, event_type: str, latency_ms: float = None, 
                  threshold_ms: float = None, destination_ip: str = '', 
                  message: str = ''):
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            timestamp = datetime.now().isoformat()
            cursor.execute('''
                INSERT INTO events 
                (timestamp, event_type, latency_ms, threshold_ms, destination_ip, message)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (timestamp, event_type, latency_ms, threshold_ms, destination_ip, message))
            conn.commit()
            conn.close()
    
    def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self.get_connection()
            # row_factory returns objects that can be converted to dict
            rows = conn.execute('''
                SELECT * FROM events ORDER BY timestamp DESC LIMIT ?
            ''', (limit,)).fetchall()
            conn.close()
            return [dict(row) for row in rows]
    
    def cleanup_old_events(self, retention_days: int = 30):
        with self.lock:
            conn = self.get_connection()
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            cursor = conn.execute('DELETE FROM events WHERE timestamp < ?', (cutoff_date.isoformat(),))
            count = cursor.rowcount
            conn.commit()
            conn.close()
            conn.close()
            return count

    def get_events_range(self, hours: int) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self.get_connection()
            cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
            rows = conn.execute('''
                SELECT * FROM events WHERE timestamp >= ? ORDER BY timestamp DESC
            ''', (cutoff,)).fetchall()
            conn.close()
            return [dict(row) for row in rows]
    
    def get_event_count(self) -> int:
        with self.lock:
            conn = self.get_connection()
            count = conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]
            conn.close()
            return count

    def log_metric(self, monitor_id, monitor_name, m_type, timestamp, value_data):
        import json
        with self.lock:
            conn = self.get_connection()
            conn.execute('''
                INSERT INTO metrics (monitor_id, monitor_name, type, timestamp, value_json)
                VALUES (?, ?, ?, ?, ?)
            ''', (monitor_id, monitor_name, m_type, timestamp, json.dumps(value_data)))
            conn.commit()
            conn.close()

    def get_metrics_range(self, hours: int) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self.get_connection()
            cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
            rows = conn.execute('''
                SELECT * FROM metrics WHERE timestamp >= ? ORDER BY timestamp ASC
            ''', (cutoff,)).fetchall()
            conn.close()
            return [dict(row) for row in rows]
