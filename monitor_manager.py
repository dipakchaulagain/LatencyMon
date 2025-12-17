import time
import threading
from typing import Callable, Optional, Dict, List
from ping3 import ping
from datetime import datetime
from snmp_manager import SNMPManager

class MonitorManager:
    """Manages multiple monitoring tasks (Ping, Bandwidth)."""
    
    def __init__(self, db, config):
        self.db = db
        self.config = config
        self.monitors: Dict[int, 'BaseMonitor'] = {}
        self.running = False
        self.lock = threading.Lock()
        self.thread = None
        
        # Event callbacks
        self.on_data_callback = None
        self.on_threshold_callback = None
        
        # SNMP Manager
        self.snmp = SNMPManager()

    def set_callbacks(self, on_data=None, on_threshold=None):
        self.on_data_callback = on_data
        self.on_threshold_callback = on_threshold

    def _monitor_loop(self):
        """Main loop that iterates through all active monitors."""
        while self.running:
            start_time = time.time()
            
            # Fetch active monitors configuration from DB to keep in sync
            # In a production system, we'd trigger updates via events, 
            # but for simplicity, we refresh configuration logic or just iterate existing objects.
            # Here we assume self.monitors is updated via add/remove methods.
            
            with self.lock:
                active_monitors = list(self.monitors.values())
            
            for monitor in active_monitors:
                try:
                    result = monitor.poll()
                    if result and self.on_data_callback:
                        self.on_data_callback(result)
                except Exception as e:
                    print(f"Error in monitor {monitor.name}: {e}")
            
            # Sleep until next second (approximate 1s global loop)
            # Individual monitors handle their own intervals
            elapsed = time.time() - start_time
            time.sleep(max(0.1, 1.0 - elapsed))

    def load_monitors(self):
        """Load all monitors from database."""
        monitor_configs = self.db.get_monitors()
        with self.lock:
            self.monitors.clear()
            for conf in monitor_configs:
                self._create_monitor_instance(conf)

    def _create_monitor_instance(self, conf):
        monitor_type = conf['type']
        if monitor_type == 'ping':
            monitor = PingMonitor(
                id=conf['id'],
                name=conf['name'],
                target=conf['target'],
                settings=conf['settings']
            )
        elif monitor_type == 'bandwidth':
            # For bandwidth, target is the specific interface ID
            # We need to look up device IP and community string
            iface = self.db.get_interface(int(conf['target']))
            if iface:
                device = self.db.get_device(iface['device_id'])
                monitor = BandwidthMonitor(
                    id=conf['id'],
                    name=conf['name'],
                    if_index=iface['if_index'],
                    device_ip=device['ip_address'],
                    community=device['community_string'],
                    snmp_manager=self.snmp,
                    settings=conf['settings']
                )
            else:
                return # Invalid target
        else:
            return

        self.monitors[conf['id']] = monitor

    def start(self):
        if not self.running:
            self.running = True
            self.load_monitors()
            self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.thread.start()
            print("Monitor Manager started")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            
    def reload_monitor(self, monitor_id: int):
        """Reload a specific monitor configuration from DB."""
        conf = self.db.get_monitor(monitor_id)
        with self.lock:
            if conf:
                self._create_monitor_instance(conf)
            elif monitor_id in self.monitors:
                del self.monitors[monitor_id]

    def remove_monitor(self, monitor_id: int):
        with self.lock:
            if monitor_id in self.monitors:
                del self.monitors[monitor_id]


class BaseMonitor:
    def __init__(self, id, name, settings):
        self.id = id
        self.name = name
        self.settings = settings
        self.last_poll_time = 0
        self.interval = float(settings.get('interval', 1.0))

    def should_poll(self) -> bool:
        return (time.time() - self.last_poll_time) >= self.interval

    def poll(self):
        if not self.should_poll():
            return None
        self.last_poll_time = time.time()
        return self._perform_poll()

    def _perform_poll(self):
        raise NotImplementedError()


class PingMonitor(BaseMonitor):
    def __init__(self, id, name, target, settings):
        super().__init__(id, name, settings)
        self.target_ip = target
        self.threshold = float(settings.get('threshold', 5.0))

    def _perform_poll(self):
        timestamp = datetime.now().isoformat()
        try:
            latency = ping(self.target_ip, timeout=1, unit='ms')
            
            if latency is None:
                return {
                    'monitor_id': self.id,
                    'monitor_name': self.name,
                    'type': 'ping',
                    'timestamp': timestamp,
                    'value': None,
                    'packet_loss': True
                }
            
            latency = round(latency, 2)
            threshold_exceeded = latency > self.threshold
            
            return {
                'monitor_id': self.id,
                'monitor_name': self.name,
                'type': 'ping',
                'timestamp': timestamp,
                'value': latency,
                'packet_loss': False,
                'threshold_exceeded': threshold_exceeded,
                'threshold': self.threshold
            }
        except Exception as e:
            print(f"Ping Error {self.target_ip}: {e}")
            return None


class BandwidthMonitor(BaseMonitor):
    def __init__(self, id, name, if_index, device_ip, community, snmp_manager, settings):
        # Default interval for SNMP usually higher (e.g. 5s)
        if 'interval' not in settings:
            settings['interval'] = 5.0
        super().__init__(id, name, settings)
        
        self.if_index = if_index
        self.device_ip = device_ip
        self.community = community
        self.snmp = snmp_manager
        
        # State for rate calculation
        self.prev_octets = None # {'in': val, 'out': val, 'time': ts}

    def _perform_poll(self):
        timestamp = datetime.now().isoformat()
        
        # Get counters
        result = self.snmp.get_interface_counters(
            self.device_ip, self.community, [self.if_index]
        )
        
        if not result or self.if_index not in result:
            return None # SNMP failure
            
        current = result[self.if_index]
        current_time = current['timestamp']
        
        data = {
            'monitor_id': self.id,
            'monitor_name': self.name,
            'type': 'bandwidth',
            'timestamp': timestamp,
            'in_bps': 0,
            'out_bps': 0
        }

        if self.prev_octets:
            time_delta = current_time - self.prev_octets['timestamp']
            
            if time_delta > 0:
                # Calculate In rate
                diff_in = current['in_octets'] - self.prev_octets['in_octets']
                # Handle 64-bit wrap (rough heuristic, exact would check snmp version capacity)
                if diff_in < 0: 
                    diff_in += 2**64 
                
                # Calculate Out rate
                diff_out = current['out_octets'] - self.prev_octets['out_octets']
                if diff_out < 0:
                    diff_out += 2**64

                # Bytes to Bits / Seconds
                data['in_bps'] = (diff_in * 8) / time_delta
                data['out_bps'] = (diff_out * 8) / time_delta
                
                # Check Threshold
                threshold_mbps = float(self.settings.get('threshold_mbps', 0))
                if threshold_mbps > 0:
                    in_mbps = data['in_bps'] / 1e6
                    out_mbps = data['out_bps'] / 1e6
                    if in_mbps > threshold_mbps or out_mbps > threshold_mbps:
                         data['threshold_exceeded'] = True
                         data['threshold'] = threshold_mbps
        
        # Update previous
        self.prev_octets = {
            'in_octets': current['in_octets'],
            'out_octets': current['out_octets'],
            'timestamp': current_time
        }
        
        return data
