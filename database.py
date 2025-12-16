import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any
import threading

class Database:
    """SQLite database management for latency monitoring events."""
    
    def __init__(self, db_file: str = 'latency_monitor.db'):
        self.db_file = db_file
        self.lock = threading.Lock()
        self.init_database()
    
    def get_connection(self):
        """Get a database connection."""
        return sqlite3.connect(self.db_file)
    
    def init_database(self):
        """Initialize database schema."""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Create events table
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
            
            # Create index on timestamp for faster queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON events(timestamp)
            ''')
            
            conn.commit()
            conn.close()
    
    def log_event(self, event_type: str, latency_ms: float = None, 
                  threshold_ms: float = None, destination_ip: str = '', 
                  message: str = ''):
        """Log a monitoring event."""
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
        """Get recent events."""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, timestamp, event_type, latency_ms, threshold_ms, 
                       destination_ip, message
                FROM events
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            events = []
            for row in rows:
                events.append({
                    'id': row[0],
                    'timestamp': row[1],
                    'event_type': row[2],
                    'latency_ms': row[3],
                    'threshold_ms': row[4],
                    'destination_ip': row[5],
                    'message': row[6]
                })
            
            return events
    
    def get_events_by_date_range(self, start_date: datetime, 
                                  end_date: datetime) -> List[Dict[str, Any]]:
        """Get events within a date range."""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, timestamp, event_type, latency_ms, threshold_ms, 
                       destination_ip, message
                FROM events
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp DESC
            ''', (start_date.isoformat(), end_date.isoformat()))
            
            rows = cursor.fetchall()
            conn.close()
            
            events = []
            for row in rows:
                events.append({
                    'id': row[0],
                    'timestamp': row[1],
                    'event_type': row[2],
                    'latency_ms': row[3],
                    'threshold_ms': row[4],
                    'destination_ip': row[5],
                    'message': row[6]
                })
            
            return events
    
    def cleanup_old_events(self, retention_days: int = 30):
        """Delete events older than retention period."""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            cursor.execute('''
                DELETE FROM events
                WHERE timestamp < ?
            ''', (cutoff_date.isoformat(),))
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            return deleted_count
    
    def get_event_count(self) -> int:
        """Get total event count."""
        with self.lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM events')
            count = cursor.fetchone()[0]
            
            conn.close()
            return count
