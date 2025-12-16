import time
import threading
from datetime import datetime
from typing import Callable, Optional
from ping3 import ping

class PingMonitor:
    """Continuous ping monitoring with latency and packet loss detection."""
    
    def __init__(self, destination_ip: str, threshold_ms: float, 
                 interval_seconds: float = 1):
        self.destination_ip = destination_ip
        self.threshold_ms = threshold_ms
        self.interval_seconds = interval_seconds
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.on_data_callback: Optional[Callable] = None
        self.on_threshold_callback: Optional[Callable] = None
        self.on_packet_loss_callback: Optional[Callable] = None
        self.lock = threading.Lock()
        
    def set_destination(self, destination_ip: str):
        """Update destination IP."""
        with self.lock:
            self.destination_ip = destination_ip
    
    def set_threshold(self, threshold_ms: float):
        """Update latency threshold."""
        with self.lock:
            self.threshold_ms = threshold_ms
    
    def set_interval(self, interval_seconds: float):
        """Update ping interval."""
        with self.lock:
            self.interval_seconds = interval_seconds
    
    def on_data(self, callback: Callable):
        """Register callback for ping data."""
        self.on_data_callback = callback
    
    def on_threshold_exceeded(self, callback: Callable):
        """Register callback for threshold violations."""
        self.on_threshold_callback = callback
    
    def on_packet_loss(self, callback: Callable):
        """Register callback for packet loss."""
        self.on_packet_loss_callback = callback
    
    def _ping_loop(self):
        """Main ping monitoring loop."""
        while self.running:
            try:
                # Get current settings (thread-safe)
                with self.lock:
                    dest_ip = self.destination_ip
                    threshold = self.threshold_ms
                    interval = self.interval_seconds
                
                # Perform ping (timeout of 2 seconds)
                start_time = time.time()
                latency = ping(dest_ip, timeout=2, unit='ms')
                timestamp = datetime.now().isoformat()
                
                if latency is None:
                    # Packet loss detected
                    if self.on_packet_loss_callback:
                        self.on_packet_loss_callback({
                            'timestamp': timestamp,
                            'destination_ip': dest_ip,
                            'message': 'Packet loss detected'
                        })
                    
                    if self.on_data_callback:
                        self.on_data_callback({
                            'timestamp': timestamp,
                            'latency_ms': None,
                            'destination_ip': dest_ip,
                            'packet_loss': True
                        })
                else:
                    # Successful ping
                    latency_ms = round(latency, 2)
                    
                    # Check threshold
                    threshold_exceeded = latency_ms > threshold
                    
                    if threshold_exceeded and self.on_threshold_callback:
                        self.on_threshold_callback({
                            'timestamp': timestamp,
                            'latency_ms': latency_ms,
                            'threshold_ms': threshold,
                            'destination_ip': dest_ip,
                            'message': f'Latency {latency_ms}ms exceeded threshold {threshold}ms'
                        })
                    
                    if self.on_data_callback:
                        self.on_data_callback({
                            'timestamp': timestamp,
                            'latency_ms': latency_ms,
                            'destination_ip': dest_ip,
                            'packet_loss': False,
                            'threshold_exceeded': threshold_exceeded
                        })
                
                # Sleep for the remaining interval time
                elapsed = time.time() - start_time
                sleep_time = max(0, interval - elapsed)
                time.sleep(sleep_time)
                
            except Exception as e:
                print(f"Ping error: {e}")
                time.sleep(interval)
    
    def start(self):
        """Start the ping monitoring thread."""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._ping_loop, daemon=True)
            self.thread.start()
            print(f"Ping monitor started for {self.destination_ip}")
    
    def stop(self):
        """Stop the ping monitoring thread."""
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join(timeout=5)
            print("Ping monitor stopped")
    
    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self.running
