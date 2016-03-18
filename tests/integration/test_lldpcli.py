import pytest
import time
import re
import platform
import json
import xml.etree.ElementTree as ET


@pytest.fixture(scope='session')
def uname():
    return "{} {} {} {}".format(
        platform.system(),
        platform.release(),
        platform.version(),
        platform.machine())


def test_text_output(lldpd1, lldpd, lldpcli, namespaces, uname):
    with namespaces(2):
        lldpd()
    with namespaces(1):
        result = lldpcli("show", "neighbors", "details")
        assert result.returncode == 0
        expected = """-------------------------------------------------------------------------------
LLDP neighbors:
-------------------------------------------------------------------------------
Interface:    eth0, via: LLDP, RID: 1, Time: 0 day, 00:00:{seconds}
  Chassis:
    ChassisID:    mac 00:00:00:00:00:02
    SysName:      ns-2.example.com
    SysDescr:     Spectacular GNU/Linux 2016 {uname}
    MgmtIP:       fe80::200:ff:fe00:2
    Capability:   Bridge, off
    Capability:   Router, {router}
    Capability:   Wlan, off
    Capability:   Station, {station}
  Port:
    PortID:       mac 00:00:00:00:00:02
    PortDescr:    eth1
-------------------------------------------------------------------------------
"""
        out = result.stdout.decode('ascii')
        seconds = re.search(r'^Interface: .*(\d\d)$',
                            out,
                            re.MULTILINE).group(1)
        router = re.search(r'^    Capability:   Router, (.*)$',
                           out,
                           re.MULTILINE).group(1)
        station = re.search(r'^    Capability:   Station, (.*)$',
                            out,
                            re.MULTILINE).group(1)
        out = re.sub(r' *$', '', out, flags=re.MULTILINE)
        assert out == expected.format(seconds=seconds,
                                      router=router,
                                      station=station,
                                      uname=uname)


@pytest.mark.skipif('JSON' not in pytest.config.lldpcli.outputs,
                    reason="JSON not supported")
def test_json_output(lldpd1, lldpd, lldpcli, namespaces, uname):
    with namespaces(2):
        lldpd()
    with namespaces(1):
        result = lldpcli("-f", "json", "show", "neighbors", "details")
        assert result.returncode == 0
        out = result.stdout.decode('ascii')
        j = json.loads(out)

        eth0 = j['lldp']['interface']['eth0']
        del eth0['age']
        del eth0['chassis']['ns-2.example.com']['capability'][3]
        del eth0['chassis']['ns-2.example.com']['capability'][1]
        expected = {"lldp": {
            "interface": {"eth0": {
                "via": "LLDP",
                "rid": "1",
                "chassis": {
                    "ns-2.example.com": {
                        "id": {
                            "type": "mac",
                            "value": "00:00:00:00:00:02"
                        },
                        "descr": "Spectacular GNU/Linux 2016 {}".format(uname),
                        "mgmt-ip": "fe80::200:ff:fe00:2",
                        "capability": [
                            {"type": "Bridge", "enabled": False},
                            {"type": "Wlan", "enabled": False},
                        ]
                    }
                },
                "port": {
                    "id": {
                        "type": "mac",
                        "value": "00:00:00:00:00:02"
                    },
                    "descr": "eth1"
                }
            }}
        }}

        assert j == expected


@pytest.mark.skipif('XML' not in pytest.config.lldpcli.outputs,
                    reason="XML not supported")
def test_xml_output(lldpd1, lldpd, lldpcli, namespaces, uname):
    with namespaces(2):
        lldpd()
    with namespaces(1):
        result = lldpcli("-f", "xml", "show", "neighbors", "details")
        assert result.returncode == 0
        out = result.stdout.decode('ascii')
        xml = ET.fromstring(out)

        age = xml.findall('./interface[1]')[0].attrib['age']
        router = xml.findall("./interface[1]/chassis/"
                           "capability[@type='Router']")[0].attrib['enabled']
        station = xml.findall("./interface[1]/chassis/"
                            "capability[@type='Station']")[0].attrib['enabled']
        expected = ET.fromstring("""<?xml version="1.0" encoding="UTF-8"?>
<lldp label="LLDP neighbors">
 <interface label="Interface" name="eth0" via="LLDP" rid="1" age="{age}">
  <chassis label="Chassis">
   <id label="ChassisID" type="mac">00:00:00:00:00:02</id>
   <name label="SysName">ns-2.example.com</name>
   <descr label="SysDescr">Spectacular GNU/Linux 2016 {uname}</descr>
   <mgmt-ip label="MgmtIP">fe80::200:ff:fe00:2</mgmt-ip>
   <capability label="Capability" type="Bridge" enabled="off"/>
   <capability label="Capability" type="Router" enabled="{router}"/>
   <capability label="Capability" type="Wlan" enabled="off"/>
   <capability label="Capability" type="Station" enabled="{station}"/>
  </chassis>
  <port label="Port">
   <id label="PortID" type="mac">00:00:00:00:00:02</id>
   <descr label="PortDescr">eth1</descr>
  </port>
 </interface>
</lldp>
        """.format(age=age,
                   router=router,
                   station=station,
                   uname=uname))
        assert ET.tostring(xml) == ET.tostring(expected)


@pytest.mark.skipif('Dot3' not in pytest.config.lldpd.features,
                    reason="Dot3 not supported")
def test_configure_one_port(lldpd1, lldpd, lldpcli, namespaces, links):
    links(namespaces(1), namespaces(2))
    with namespaces(2):
        lldpd()
        result = lldpcli(*("configure ports eth3 dot3 power "
                           "pse supported enabled paircontrol powerpairs "
                           "spare class class-3").split())
        assert result.returncode == 0
        time.sleep(3)
    with namespaces(1):
        out = lldpcli("-f", "keyvalue", "show", "neighbors", "details")
        assert out['lldp.eth0.port.descr'] == 'eth1'
        assert 'lldp.eth0.port.power.device-type' not in out
        assert out['lldp.eth2.port.descr'] == 'eth3'
        assert out['lldp.eth2.port.power.device-type'] == 'PSE'


@pytest.mark.skipif('Dot3' not in pytest.config.lldpd.features,
                    reason="Dot3 not supported")
def test_new_port_take_default(lldpd1, lldpd, lldpcli, namespaces, links):
    with namespaces(2):
        lldpd()
        result = lldpcli(*("configure dot3 power "
                           "pse supported enabled paircontrol powerpairs "
                           "spare class class-3").split())
        assert result.returncode == 0
        time.sleep(3)
    with namespaces(1):
        # Check this worked
        out = lldpcli("-f", "keyvalue", "show", "neighbors", "details")
        assert out['lldp.eth0.port.descr'] == 'eth1'
        assert out['lldp.eth0.port.power.device-type'] == 'PSE'
    links(namespaces(1), namespaces(2))
    time.sleep(6)
    with namespaces(1):
        out = lldpcli("-f", "keyvalue", "show", "neighbors", "details")
        assert out['lldp.eth2.port.descr'] == 'eth3'
        assert out['lldp.eth2.port.power.device-type'] == 'PSE'


@pytest.mark.skipif('Dot3' not in pytest.config.lldpd.features,
                    reason="Dot3 not supported")
def test_port_keep_configuration(lldpd1, lldpd, lldpcli, namespaces, links):
    links(namespaces(1), namespaces(2))
    with namespaces(2):
        lldpd()
        result = lldpcli(*("configure ports eth3 dot3 power "
                           "pse supported enabled paircontrol powerpairs "
                           "spare class class-3").split())
        assert result.returncode == 0
        time.sleep(3)
        links.down('eth3')
        time.sleep(4)
        links.up('eth3')
        time.sleep(4)
    with namespaces(1):
        out = lldpcli("-f", "keyvalue", "show", "neighbors", "details")
        assert out['lldp.eth2.port.descr'] == 'eth3'
        assert out['lldp.eth2.port.power.device-type'] == 'PSE'
