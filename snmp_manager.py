from pysnmp.hlapi import *
import time

class SNMPManager:
    """Handles SNMP operations for discovery and polling (Synchronous/Legacy)."""
    
    def __init__(self, timeout: float = 1.0, retries: int = 1):
        self.timeout = timeout
        self.retries = retries

    def _get_engine(self):
        return SnmpEngine()

    def _get_community(self, community_string: str, version: int = 1):
        # Version 0 = SNMPv1, Version 1 = SNMPv2c
        mp_model = 1 if version == 2 else 0
        return CommunityData(community_string, mpModel=mp_model)

    def _get_target(self, ip_address: str, port: int = 161):
        return UdpTransportTarget((ip_address, port), timeout=self.timeout, retries=self.retries)

    def validate_connection(self, ip_address: str, community_string: str) -> bool:
        """
        Validate SNMP connection by querying sysDescr.
        OID: 1.3.6.1.2.1.1.1.0 (sysDescr)
        """
        try:
            iterator = getCmd(
                self._get_engine(),
                self._get_community(community_string, 2), # Default to v2c
                self._get_target(ip_address),
                ContextData(),
                ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0'))
            )

            errorIndication, errorStatus, errorIndex, varBinds = next(iterator)

            if errorIndication:
                print(f"SNMP Error: {errorIndication}")
                return False
            elif errorStatus:
                print(f"SNMP Error: {errorStatus.prettyPrint()}")
                return False
            return True
        except Exception as e:
            print(f"SNMP Exception: {e}")
            return False

    def discover_interfaces(self, ip_address: str, community_string: str) -> list:
        """
        Discover network interfaces using IF-MIB.
        Returns a list of dicts with name, index, speed, description.
        """
        try:
            interfaces = {}
            # OIDs to walk
            oids_to_walk = {
                'name': '1.3.6.1.2.1.31.1.1.1.1',     # ifName
                'alias': '1.3.6.1.2.1.31.1.1.1.18',   # ifAlias
                'speed': '1.3.6.1.2.1.2.2.1.5'        # ifSpeed (32-bit)
            }
            results = {'name': {}, 'alias': {}, 'speed': {}}

            for key, oid in oids_to_walk.items():
                iterator = nextCmd(
                    self._get_engine(),
                    self._get_community(community_string, 2),
                    self._get_target(ip_address),
                    ContextData(),
                    ObjectType(ObjectIdentity(oid)),
                    lexicographicMode=False
                )

                for errorIndication, errorStatus, errorIndex, varBinds in iterator:
                    if errorIndication or errorStatus:
                        continue
                    
                    for varBind in varBinds:
                        # OID structure: base_oid.index
                        oid_obj, value = varBind
                        index = int(oid_obj[-1])
                        results[key][index] = str(value)

            # Merge results
            final_interfaces = []
            for idx, name in results['name'].items():
                final_interfaces.append({
                    'index': idx,
                    'name': name,
                    'description': results['alias'].get(idx, ''),
                    'speed': int(results['speed'].get(idx, 0))
                })
            return final_interfaces
        except Exception as e:
            print(f"Discovery Failed: {e}")
            return []

    def get_interface_counters(self, ip_address: str, community_string: str, indices: list) -> dict:
        """
        Get In/Out octets for specific interface indices.
        Prioritizes 64-bit HC counters.
        """
        try:
            query_objects = []
            for idx in indices:
                query_objects.append(ObjectType(ObjectIdentity(f'1.3.6.1.2.1.31.1.1.1.6.{idx}')))
                query_objects.append(ObjectType(ObjectIdentity(f'1.3.6.1.2.1.31.1.1.1.10.{idx}')))
                
            iterator = getCmd(
                self._get_engine(),
                self._get_community(community_string, 2),
                self._get_target(ip_address),
                ContextData(),
                *query_objects
            )
            
            errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
            
            result = {}
            if not errorIndication and not errorStatus:
                for i in range(0, len(varBinds), 2):
                    in_var = varBinds[i]
                    out_var = varBinds[i+1]
                    idx = int(in_var[0][-1])
                    
                    result[idx] = {
                        'in_octets': int(in_var[1]),
                        'out_octets': int(out_var[1]),
                        'timestamp': time.time()
                    }
                    
            return result
        except Exception as e:
            print(f"Counters Failed: {e}")
            return {}
