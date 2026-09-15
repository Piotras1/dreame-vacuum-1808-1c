"""Dreame MC1808 (dreame.vacuum.mc1808) local miIO/MiOT client.

This single file replaces what used to be an 8-file `miio/` package
(a 1:1 copy of the upstream python-miio project's internal layout:
exceptions.py, protocol.py, miioprotocol.py, device.py, miot_device.py,
click_common.py, dreamevacuum.py). Since this integration only ever
supports one device model and no longer needs to track upstream, there is
no benefit to keeping that structure - it only made the code harder to
navigate. Nothing here is Home Assistant specific; this module has zero
dependency on `homeassistant` and can be imported/tested standalone.

Layered from bottom to top:
    exceptions   -> DeviceException, DeviceError, RecoverableError
    protocol     -> Message struct + AES encrypt/decrypt (Utils)
    MiIOProtocol -> sends/receives UDP packets, handles retries
    Device       -> generic miIO device (raw_command, info, get_properties)
    MiotDevice   -> adds MiOT-style property dataclasses (get/set via siid/piid)
    DreameVacuum -> the actual MC1808 device: status + all its actions
"""
from __future__ import annotations

import binascii
import calendar
import codecs
import datetime
import hashlib
import json
import logging
import socket
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import construct
from construct import (
    Adapter,
    Bytes,
    Checksum,
    Const,
    Default,
    GreedyBytes,
    Hex,
    IfThenElse,
    Int16ub,
    Int32ub,
    Pointer,
    RawCopy,
    Rebuild,
    Struct,
)
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)


def command(*args, **kwargs):
    """No-op decorator kept only for readability/documentation of device
    actions below (`@command()` marks "this is a device action/property").
    The original upstream project used it to auto-register a `click`-based
    CLI; Home Assistant never calls into that, so it's just a marker here.
    """

    def decorator(func):
        return func

    return decorator


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DeviceException(Exception):
    """Exception wrapping any communication errors with the device."""

    pass


class DeviceError(DeviceException):
    """Exception communicating an error delivered by the target device."""

    def __init__(self, error):
        self.code = error.get("code")
        self.message = error.get("message")


class RecoverableError(DeviceError):
    """Exception communicating a recoverable error delivered by the target device."""

    pass


# ---------------------------------------------------------------------------
# miIO wire protocol: AES encryption + packet (de)serialization
# ---------------------------------------------------------------------------


class Utils:
    """Encryption helpers, adapted from the original xpn.py code by gst666."""

    @staticmethod
    def verify_token(token: bytes):
        """Checks if the given token is of correct type and length."""
        if not isinstance(token, bytes):
            raise TypeError("Token must be bytes")
        if len(token) != 16:
            raise ValueError("Wrong token length")

    @staticmethod
    def md5(data: bytes) -> bytes:
        """Calculates a md5 hashsum for the given bytes object."""
        checksum = hashlib.md5()
        checksum.update(data)
        return checksum.digest()

    @staticmethod
    def key_iv(token: bytes) -> Tuple[bytes, bytes]:
        """Generate an IV used for encryption based on given token."""
        key = Utils.md5(token)
        iv = Utils.md5(key + token)
        return key, iv

    @staticmethod
    def encrypt(plaintext: bytes, token: bytes) -> bytes:
        """Encrypt plaintext with a given token."""
        if not isinstance(plaintext, bytes):
            raise TypeError("plaintext requires bytes")
        Utils.verify_token(token)
        key, iv = Utils.key_iv(token)
        padder = padding.PKCS7(128).padder()

        padded_plaintext = padder.update(plaintext) + padder.finalize()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())

        encryptor = cipher.encryptor()
        return encryptor.update(padded_plaintext) + encryptor.finalize()

    @staticmethod
    def decrypt(ciphertext: bytes, token: bytes) -> bytes:
        """Decrypt ciphertext with a given token."""
        if not isinstance(ciphertext, bytes):
            raise TypeError("ciphertext requires bytes")
        Utils.verify_token(token)
        key, iv = Utils.key_iv(token)
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())

        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        unpadder = padding.PKCS7(128).unpadder()
        unpadded_plaintext = unpadder.update(padded_plaintext)
        unpadded_plaintext += unpadder.finalize()
        return unpadded_plaintext

    @staticmethod
    def checksum_field_bytes(ctx: Dict[str, Any]) -> bytearray:
        """Gather bytes for checksum calculation."""
        x = bytearray(ctx["header"].data)
        x += ctx["_"]["token"]
        if "data" in ctx:
            x += ctx["data"].data
        return x

    @staticmethod
    def get_length(x) -> int:
        """Return total packet length."""
        datalen = x._.data.length  # type: int
        return datalen + 32

    @staticmethod
    def is_hello(x) -> bool:
        """Return if packet is a hello packet."""
        if "length" in x:
            val = x["length"]
        else:
            val = x.header.value["length"]
        return bool(val == 32)


class TimeAdapter(Adapter):
    """Adapter for timestamp conversion."""

    def _encode(self, obj, context, path):
        return calendar.timegm(obj.timetuple())

    def _decode(self, obj, context, path):
        return datetime.datetime.utcfromtimestamp(obj)


class EncryptionAdapter(Adapter):
    """Adapter to handle communication encryption."""

    def _encode(self, obj, context, path):
        """Encrypt the given payload with the token stored in the context."""
        return Utils.encrypt(
            json.dumps(obj).encode("utf-8") + b"\x00", context["_"]["token"]
        )

    def _decode(self, obj, context, path):
        """Decrypts the given payload with the token stored in the context."""
        try:
            decrypted = Utils.decrypt(obj, context["_"]["token"])
            decrypted = decrypted.rstrip(b"\x00")
        except Exception:
            _LOGGER.debug("Unable to decrypt, returning raw bytes: %s", obj)
            return obj

        # list of adaption functions for malformed json payload (quirks)
        decrypted_quirks = [
            lambda decrypted_bytes: decrypted_bytes,
            lambda decrypted_bytes: decrypted_bytes.replace(
                b',,"otu_stat"', b',"otu_stat"'
            ),
            lambda decrypted_bytes: decrypted_bytes[: decrypted_bytes.rfind(b"\x00")]
            if b"\x00" in decrypted_bytes
            else decrypted_bytes,
        ]

        for i, quirk in enumerate(decrypted_quirks):
            decoded = quirk(decrypted).decode("utf-8")
            try:
                return json.loads(decoded)
            except Exception as ex:
                if i == len(decrypted_quirks) - 1:
                    _LOGGER.error("unable to parse json '%s': %s", decoded, ex)

        return None


Message = Struct(
    # for building we need data before anything else.
    "data" / Pointer(32, RawCopy(EncryptionAdapter(GreedyBytes))),
    "header"
    / RawCopy(
        Struct(
            Const(0x2131, Int16ub),
            "length" / Rebuild(Int16ub, Utils.get_length),
            "unknown" / Default(Int32ub, 0x00000000),
            "device_id" / Hex(Bytes(4)),
            "ts" / TimeAdapter(Default(Int32ub, datetime.datetime.utcnow())),
        )
    ),
    "checksum"
    / IfThenElse(
        Utils.is_hello,
        Bytes(16),
        Checksum(Bytes(16), Utils.md5, Utils.checksum_field_bytes),
    ),
)


class MiIOProtocol:
    """Sends/receives miIO UDP packets, handles handshake and retries."""

    def __init__(
        self,
        ip: str = None,
        token: str = None,
        start_id: int = 0,
        debug: int = 0,
        lazy_discover: bool = True,
    ) -> None:
        self.ip = ip
        self.port = 54321
        if token is None:
            token = 32 * "0"
        if token is not None:
            self.token = bytes.fromhex(token)
        self.debug = debug
        self.lazy_discover = lazy_discover

        self._timeout = 5
        self._discovered = False
        self._device_ts = None  # type: datetime.datetime
        self.__id = start_id
        self._device_id = None

    def send_handshake(self) -> Message:
        """Send a handshake to the device; also used regularly to keep the
        connection usable. Raises DeviceException if discovery fails."""
        m = MiIOProtocol.discover(self.ip)
        if m is not None:
            self._device_id = m.header.value.device_id
            self._device_ts = m.header.value.ts
            self._discovered = True
            if self.debug > 1:
                _LOGGER.debug(m)
            _LOGGER.debug(
                "Discovered %s with ts: %s, token: %s",
                binascii.hexlify(self._device_id).decode(),
                self._device_ts,
                codecs.encode(m.checksum, "hex"),
            )
        else:
            _LOGGER.error("Unable to discover a device at address %s", self.ip)
            raise DeviceException("Unable to discover the device %s" % self.ip)

        return m

    @staticmethod
    def discover(addr: str = None) -> Any:
        """Scan for devices in the network by sending a handshake to the
        broadcast address on port 54321 (or unicast, if addr is given)."""
        timeout = 5
        is_broadcast = addr is None
        seen_addrs = []  # type: List[str]
        if is_broadcast:
            addr = "<broadcast>"
            is_broadcast = True
            _LOGGER.info("Sending discovery to %s with timeout of %ss..", addr, timeout)
        # magic, length 32
        helobytes = bytes.fromhex(
            "21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
        )

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(timeout)
        s.sendto(helobytes, (addr, 54321))
        while True:
            try:
                data, addr = s.recvfrom(1024)
                m = Message.parse(data)  # type: Message
                _LOGGER.debug("Got a response: %s", m)
                if not is_broadcast:
                    return m

                if addr[0] not in seen_addrs:
                    _LOGGER.info(
                        "  IP %s (ID: %s) - token: %s",
                        addr[0],
                        binascii.hexlify(m.header.value.device_id).decode(),
                        codecs.encode(m.checksum, "hex"),
                    )
                    seen_addrs.append(addr[0])
            except socket.timeout:
                if is_broadcast:
                    _LOGGER.info("Discovery done")
                return  # ignore timeouts on discover
            except Exception as ex:
                _LOGGER.warning("error while reading discover results: %s", ex)
                break

    def send(self, command: str, parameters: Any = None, retry_count=3) -> Any:
        """Build and send the given command, retrying on failure."""
        if not self.lazy_discover or not self._discovered:
            self.send_handshake()

        cmd = {"id": self._id, "method": command}

        if parameters is not None:
            cmd["params"] = parameters
        else:
            cmd["params"] = []

        send_ts = self._device_ts + datetime.timedelta(seconds=1)
        header = {
            "length": 0,
            "unknown": 0x00000000,
            "device_id": self._device_id,
            "ts": send_ts,
        }

        msg = {"data": {"value": cmd}, "header": {"value": header}, "checksum": 0}
        m = Message.build(msg, token=self.token)
        _LOGGER.debug("%s:%s >>: %s", self.ip, self.port, cmd)
        if self.debug > 1:
            _LOGGER.debug(
                "send (timeout %s): %s",
                self._timeout,
                Message.parse(m, token=self.token),
            )

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(self._timeout)

        try:
            s.sendto(m, (self.ip, self.port))
        except OSError as ex:
            _LOGGER.error("failed to send msg: %s", ex)
            raise DeviceException from ex

        try:
            data, addr = s.recvfrom(1024)
            m = Message.parse(data, token=self.token)
            self._device_ts = m.header.value.ts
            if self.debug > 1:
                _LOGGER.debug("recv from %s: %s", addr[0], m)

            self.__id = m.data.value["id"]
            _LOGGER.debug(
                "%s:%s (ts: %s, id: %s) << %s",
                self.ip,
                self.port,
                m.header.value.ts,
                m.data.value["id"],
                m.data.value,
            )
            if "error" in m.data.value:
                error = m.data.value["error"]
                if "code" in error and error["code"] == -30001:
                    raise RecoverableError(error)
                raise DeviceError(error)

            try:
                return m.data.value["result"]
            except KeyError:
                return m.data.value
        except construct.core.ChecksumError as ex:
            raise DeviceException(
                "Got checksum error which indicates use "
                "of an invalid token. "
                "Please check your token!"
            ) from ex
        except OSError as ex:
            if retry_count > 0:
                _LOGGER.debug(
                    "Retrying with incremented id, retries left: %s", retry_count
                )
                self.__id += 100
                self._discovered = False
                return self.send(command, parameters, retry_count - 1)

            _LOGGER.error("Got error when receiving: %s", ex)
            raise DeviceException("No response from the device") from ex

        except RecoverableError as ex:
            if retry_count > 0:
                _LOGGER.debug(
                    "Retrying to send failed command, retries left: %s", retry_count
                )
                return self.send(command, parameters, retry_count - 1)

            _LOGGER.error("Got error when receiving: %s", ex)
            raise DeviceException("Unable to recover failed command") from ex

    @property
    def _id(self) -> int:
        """Increment and return the sequence id."""
        self.__id += 1
        if self.__id >= 9999:
            self.__id = 1
        return self.__id

    @property
    def raw_id(self):
        return self.__id


# ---------------------------------------------------------------------------
# Generic miIO device
# ---------------------------------------------------------------------------


class DeviceType(Enum):
    """Device type changes the used methods for property getting."""

    MiIO = 0
    MiOT = 1


class UpdateState(Enum):
    Downloading = "downloading"
    Installing = "installing"
    Failed = "failed"
    Idle = "idle"


class DeviceInfo:
    """Container of miIO device information (model, MAC, fw/hw versions)."""

    def __init__(self, data):
        self.data = data

    def __repr__(self):
        return "%s v%s (%s) @ %s - token: %s" % (
            self.data["model"],
            self.data["fw_ver"],
            self.data["mac"],
            self.network_interface["localIp"],
            self.data["token"],
        )

    def __json__(self):
        return self.data

    @property
    def network_interface(self):
        return self.data["netif"]

    @property
    def accesspoint(self):
        return self.data["ap"]

    @property
    def model(self) -> Optional[str]:
        if self.data["model"] is not None:
            return self.data["model"]
        return None

    @property
    def firmware_version(self) -> Optional[str]:
        if self.data["fw_ver"] is not None:
            return self.data["fw_ver"]
        return None

    @property
    def hardware_version(self) -> Optional[str]:
        if self.data["hw_ver"] is not None:
            return self.data["hw_ver"]
        return None

    @property
    def mac_address(self) -> Optional[str]:
        if self.data["mac"] is not None:
            return self.data["mac"]
        return None

    @property
    def raw(self):
        return self.data


class Device:
    """Base class for all device implementations, providing the basic
    miIO protocol handling. Not meant to be used directly."""

    def __init__(
        self,
        ip: str = None,
        token: str = None,
        start_id: int = 0,
        debug: int = 0,
        lazy_discover: bool = True,
    ) -> None:
        self.ip = ip
        self.token = token
        self._protocol = MiIOProtocol(ip, token, start_id, debug, lazy_discover)
        self.device_type = DeviceType.MiIO

    def send(self, command: str, parameters: Any = None, retry_count=3) -> Any:
        return self._protocol.send(command, parameters, retry_count)

    def send_handshake(self):
        return self._protocol.send_handshake()

    @command()
    def raw_command(self, command, parameters):
        """Send a raw command to the device."""
        return self._protocol.send(command, parameters)

    @command()
    def info(self) -> DeviceInfo:
        """Get miIO protocol information from the device."""
        return DeviceInfo(self._protocol.send("miIO.info"))

    def update(self, url: str, md5: str):
        """Start an OTA update."""
        payload = {
            "mode": "normal",
            "install": "1",
            "app_url": url,
            "file_md5": md5,
            "proc": "dnld install",
        }
        return self._protocol.send("miIO.ota", payload)[0] == "ok"

    def update_progress(self) -> int:
        """Return current update progress [0-100]."""
        return self._protocol.send("miIO.get_ota_progress")[0]

    def update_state(self):
        """Return current update state."""
        return UpdateState(self._protocol.send("miIO.get_ota_state")[0])

    def configure_wifi(self, ssid, password, uid=0, extra_params=None):
        """Configure the wifi settings."""
        if extra_params is None:
            extra_params = {}
        params = {"ssid": ssid, "passwd": password, "uid": uid, **extra_params}
        return self._protocol.send("miIO.config_router", params)[0]

    def get_properties(self, properties, *, max_properties=None):
        """Request properties in slices based on given max_properties."""
        if self.device_type == DeviceType.MiOT:
            get_property_method = "get_properties"
        else:
            get_property_method = "get_prop"

        _props = properties.copy()
        values = []
        while _props:
            try:
                properties_to_request = _props[:max_properties]
                values.extend(self.send(get_property_method, properties_to_request))
            except DeviceException:
                _LOGGER.error("Unable to request properties %s", properties_to_request)
                values.append(["request-failed"] * max_properties)
            if max_properties is None:
                break

            _props[:] = _props[max_properties:]

        properties_count = len(properties)
        values_count = len(values)
        if properties_count != values_count:
            _LOGGER.debug(
                "Count (%s) of requested properties does not match the "
                "count (%s) of received values.",
                properties_count,
                values_count,
            )

        return values


# ---------------------------------------------------------------------------
# MiOT device (property dataclasses via siid/piid)
# ---------------------------------------------------------------------------


@dataclass
class MiotInfo:
    """Container for common MiotInfo service."""

    _siid = 1
    _max_properties = 1  # some devices respond with broken json otherwise

    manufacturer: str = field(metadata={"piid": 1})
    model: str = field(metadata={"piid": 2})
    serial_number: str = field(metadata={"piid": 3})
    firmware_version: str = field(metadata={"piid": 4})


class MiotDevice(Device):
    """Main class representing a MIoT device."""

    def __init__(
        self,
        ip: str = None,
        token: str = None,
        start_id: int = 0,
        debug: int = 0,
        lazy_discover: bool = True,
    ) -> None:
        super().__init__(ip, token, start_id, debug, lazy_discover)
        self.device_type = DeviceType.MiOT

    @command()
    def miot_info(self) -> MiotInfo:
        """Return common miot information."""
        return self.get_properties_for_dataclass(MiotInfo)

    def get_properties_for_dataclass(self, cls):
        """Run a query to fill property container."""
        fields = cls.__dataclass_fields__
        property_mapping = {}

        for field_name in fields:
            field_meta = fields[field_name].metadata

            if "piid" not in field_meta:
                continue
            piid = field_meta["piid"]

            siid = field_meta.get("siid", getattr(cls, "_siid", None))
            if siid is None:
                raise DeviceException(
                    f"no siid defined for {field_name} or for class {cls}"
                )

            property_mapping[field_name] = {"siid": siid, "piid": piid}

        response = {
            prop["did"]: prop["value"] if prop["code"] == 0 else None
            for prop in self.get_properties_for_mapping(
                property_mapping, max_properties=cls._max_properties
            )
        }

        return cls(**response)

    def set_property(self, **kwargs):
        """Helper to set properties using the device specific mapping."""
        if getattr(self, "_MAPPING") is None:
            raise DeviceException("Device class does not have _MAPPING")

        return self.set_properties_from_dataclass(self._MAPPING(**kwargs))

    def set_properties_from_dataclass(self, obj):
        """Set properties as defined in the given dataclass object."""
        fields = obj.__dataclass_fields__
        properties_to_set = []

        for field_name in fields:
            field_meta = fields[field_name].metadata

            if "piid" not in field_meta:
                continue

            piid = field_meta["piid"]

            siid = field_meta.get("siid", getattr(obj, "_siid", None))
            if siid is None:
                raise DeviceException(
                    f"no siid defined for {field_name} or for class {obj.__class__}"
                )

            value = obj.__getattribute__(field_name)
            if value is None:
                continue

            properties_to_set.append(
                {"siid": siid, "piid": piid, "did": field_name, "value": value}
            )

        if not properties_to_set:
            raise DeviceException("No values to set!")

        _LOGGER.debug("Going to set %s" % properties_to_set)
        return self.send("set_properties", properties_to_set)

    def get_properties_for_mapping(self, property_mapping, *, max_properties=15) -> list:
        """Retrieve raw properties based on mapping."""
        # We send property key in "did" because it's sent back via response
        # and we can identify the property.
        properties = [{"did": k, **v} for k, v in property_mapping.items()]
        return self.get_properties(properties, max_properties=max_properties)

    def set_property_from_mapping(self, property_mapping, property_key: str, value):
        """Sets property value."""
        return self.send(
            "set_properties",
            [{"did": property_key, **property_mapping[property_key], "value": value}],
        )


# ---------------------------------------------------------------------------
# Dreame MC1808 vacuum
# ---------------------------------------------------------------------------


class ChargeStatus(Enum):
    Charging = 1
    Not_charging = 2
    Charging2 = 4
    Go_charging = 5


class Error(Enum):
    NoError = 0
    Drop = 1
    Cliff = 2
    Bumper = 3
    Gesture = 4
    Bumper_repeat = 5
    Drop_repeat = 6
    Optical_flow = 7
    No_box = 8
    No_tankbox = 9
    Waterbox_empty = 10
    Box_full = 11
    Brush = 12
    Side_brush = 13
    Fan = 14
    Left_wheel_motor = 15
    Right_wheel_motor = 16
    Turn_suffocate = 17
    Forward_suffocate = 18
    Charger_get = 19
    Battery_low = 20
    Charge_fault = 21
    Battery_percentage = 22
    Heart = 23
    Camera_occlusion = 24
    Camera_fault = 25
    Event_battery = 26
    Forward_looking = 27
    Gyroscope = 28


class VacuumStatus(Enum):
    Sweeping = 1
    Idle = 2
    Paused = 3
    Error = 4
    Go_charging = 5
    Charging = 6


class VacuumSpeed(Enum):
    """Fan speeds, same as for ViomiVacuum."""

    Silent = 0
    Standard = 1
    Medium = 2
    Turbo = 3


@dataclass
class DreameStatus:
    _max_properties = 14

    # siid 2 (Battery)
    battery: int = field(
        metadata={"siid": 2, "piid": 1, "access": ["read", "notify"]}, default=None
    )
    state: int = field(
        metadata={
            "siid": 2,
            "piid": 2,
            "access": ["read", "notify"],
            "enum": ChargeStatus,
        },
        default=None,
    )
    # siid 3 (Robot Cleaner)
    error: int = field(
        metadata={"siid": 3, "piid": 1, "access": ["read", "notify"], "enum": Error},
        default=None,
    )
    status: int = field(
        metadata={
            "siid": 3,
            "piid": 2,
            "access": ["read", "notify"],
            "enum": VacuumStatus,
        },
        default=None,
    )
    # siid 26 (Main Cleaning Brush)
    brush_left_time: int = field(
        metadata={"siid": 26, "piid": 1, "access": ["read", "notify"]}, default=None
    )
    brush_life_level: int = field(
        metadata={"siid": 26, "piid": 2, "access": ["read", "notify"]}, default=None
    )
    # siid 27 (Filter)
    filter_life_level: int = field(
        metadata={"siid": 27, "piid": 1, "access": ["read", "notify"]}, default=None
    )
    filter_left_time: int = field(
        metadata={"siid": 27, "piid": 2, "access": ["read", "notify"]}, default=None
    )
    # siid 28 (Side Cleaning Brush)
    brush_left_time2: int = field(
        metadata={"siid": 28, "piid": 1, "access": ["read", "notify"]}, default=None
    )
    brush_life_level2: int = field(
        metadata={"siid": 28, "piid": 2, "access": ["read", "notify"]}, default=None
    )
    # siid 18 (clean)
    operating_mode: int = field(
        metadata={"siid": 18, "piid": 1, "access": ["read", "notify"]}, default=None
    )
    area: str = field(
        metadata={"siid": 18, "piid": 3, "access": ["read", "write"]}, default=None
    )
    timer: str = field(
        metadata={"siid": 18, "piid": 2, "access": ["read", "write"]}, default=None
    )
    fan_speed: int = field(
        metadata={
            "siid": 18,
            "piid": 6,
            "access": ["read", "write", "notify"],
            "enum": VacuumSpeed,
        },
        default=None,
    )
    # siid 18 (clean) - water-box status: read-only per spec (access "N"
    # only - notify - not formally "R", so it may not respond reliably to
    # a plain get_properties query on real hardware; exposed as best-effort).
    water_box: int = field(
        metadata={"siid": 18, "piid": 9, "access": ["notify"]}, default=None
    )
    # siid 18 (clean) - mop water level. Documented as read-only (access
    # "R"/"N" - no "W"): the spec gives no supported way to *set* this via
    # a plain property write, so we only expose it for display.
    mop_mode: int = field(
        metadata={"siid": 18, "piid": 20, "access": ["read", "notify"]},
        default=None,
    )
    last_clean: int = field(
        metadata={"siid": 18, "piid": 13, "access": ["read", "notify"]}, default=None
    )
    total_clean_count: int = field(
        metadata={"siid": 18, "piid": 14, "access": ["read", "notify"]}, default=None
    )
    total_area: int = field(
        metadata={"siid": 18, "piid": 15, "access": ["read", "notify"]}, default=None
    )
    total_log_start: int = field(
        metadata={"siid": 18, "piid": 16, "access": ["read", "notify"]}, default=None
    )
    button_led: int = field(
        metadata={"siid": 18, "piid": 17, "access": ["read", "notify"]}, default=None
    )
    clean_success: int = field(
        metadata={"siid": 18, "piid": 18, "access": ["read", "notify"]}, default=None
    )
    # siid 19 (consumable)
    life_sieve: str = field(
        metadata={"siid": 19, "piid": 1, "access": ["read", "write"]}, default=None
    )
    life_brush_side: str = field(
        metadata={"siid": 19, "piid": 2, "access": ["read", "write"]}, default=None
    )
    life_brush_main: str = field(
        metadata={"siid": 19, "piid": 3, "access": ["read", "write"]}, default=None
    )
    # siid 20 (annoy / do-not-disturb)
    dnd_enabled: bool = field(
        metadata={"siid": 20, "piid": 1, "access": ["read", "write"]}, default=None
    )
    dnd_start_time: str = field(
        metadata={"siid": 20, "piid": 2, "access": ["read", "write"]}, default=None
    )
    dnd_stop_time: str = field(
        metadata={"siid": 20, "piid": 3, "access": ["read", "write"]}, default=None
    )
    # siid 23 (map)
    map_view: str = field(
        metadata={"siid": 23, "piid": 1, "access": ["read", "notify"]}, default=None
    )
    # siid 24 (audio)
    audio_volume: int = field(
        metadata={"siid": 24, "piid": 1, "access": ["read", "write", "notify"]},
        default=None,
    )
    audio_language: str = field(
        metadata={"siid": 24, "piid": 3, "access": ["read", "write"]}, default=None
    )
    # siid 25
    timezone: str = field(
        metadata={"siid": 25, "piid": 1, "access": ["read", "notify"]}, default=None
    )


class DreameVacuum(MiotDevice):
    """Support for the Dreame vacuum (1C STYTJ01ZHM, dreame.vacuum.mc1808)."""

    _MAPPING = DreameStatus

    @command()
    def status(self) -> DreameStatus:
        return self.get_properties_for_dataclass(DreameStatus)

    def call_action(self, siid, aiid, params=None):
        if params is None:
            params = []
        payload = {
            "did": f"call-{siid}-{aiid}",
            "siid": siid,
            "aiid": aiid,
            "in": params,
        }
        return self.send("action", payload)

    @command()
    def set_fan_speed(self, speed):
        """Set fan speed."""
        return self.set_property(fan_speed=speed)

    # siid 2 (Battery) - aiid 1 Start Charge
    @command()
    def return_home(self) -> None:
        return self.call_action(2, 1)

    # siid 3 (Robot Cleaner)
    @command()
    def start_sweep(self) -> None:
        return self.call_action(3, 1)

    @command()
    def stop_sweeping(self) -> None:
        return self.call_action(3, 2)

    # siid 17 (Identify)
    @command()
    def find(self) -> None:
        """Find the robot."""
        return self.call_action(17, 1)

    # siid 26 (Main Cleaning Brush)
    @command()
    def reset_brush_life(self) -> None:
        return self.call_action(26, 1)

    # siid 27 (Filter)
    @command()
    def reset_filter_life(self) -> None:
        return self.call_action(27, 1)

    # siid 28 (Side Cleaning Brush)
    @command()
    def reset_brush_life2(self) -> None:
        return self.call_action(28, 1)

    # siid 18 (clean)
    @command()
    def start(self) -> None:
        """Start cleaning."""
        # TODO: find out other values
        payload = [{"piid": 1, "value": 2}]
        return self.call_action(18, 1, payload)

    @command()
    def stop(self) -> None:
        """Stop cleaning."""
        return self.call_action(18, 2)

    @command()
    def zone_cleanup(self, coords) -> None:
        """Start zone cleaning."""
        payload = [{"piid": 1, "value": 19}, {"piid": 21, "value": coords}]
        return self.call_action(18, 1, payload)

    @command()
    def segment_cleanup(self, room_ids, repeats=1, fan_speed=1) -> None:
        """Clean specific room/segment IDs.

        EXPERIMENTAL - sourced from a community-documented MIoT config
        specifically for dreame.vacuum.mc1808 (GitHub discussion:
        PiotrMachowski/lovelace-xiaomi-vacuum-map-card#406, comment by
        @rogodra / @StarterCraft), not independently verified against a
        physical device by this project. At least one user in that same
        thread reported getting a "success" response with no physical
        movement on their unit. Test carefully on real hardware, starting
        with a single room, before relying on this.

        room_ids: list of int room/segment IDs (from e.g. Xiaomi Cloud Map
        Extractor). repeats: cleaning passes per room (1-3 typical).
        fan_speed: 0=Silent, 1=Standard, 2=Medium, 3=Turbo.
        """
        selects = [[room_id, repeats, fan_speed, 3, 1] for room_id in room_ids]
        payload = [
            {"piid": 1, "value": 18},
            {"piid": 21, "value": json.dumps({"selects": selects})},
        ]
        return self.call_action(18, 1, payload)

    # siid 21 (remote)
    @command()
    def start_remote(self) -> None:
        return self.call_action(21, 1)

    @command()
    def stop_remote(self) -> None:
        return self.call_action(21, 2)

    @command()
    def exit_remote(self) -> None:
        return self.call_action(21, 3)

    # siid 23 (map)
    @command()
    def map_req(self) -> None:
        return self.call_action(23, 1)

    # siid 24 (audio)
    @command()
    def audio_position(self, percent) -> None:
        """TODO."""
        return self.set_property(audio_volume=percent)

    @command()
    def install_voice_pack(self) -> None:
        """Install given voice pack."""
        payload = [
            {"piid": 3, "value": "EN"},  # language code
            {"piid": 4, "value": "http://url"},
            {"piid": 5, "value": "md5sum for the pack"},
            {"piid": 6, "value": "size of the pack"},
        ]
        return self.call_action(24, 2, payload)

    @command()
    def test_sound(self) -> None:
        return self.call_action(24, 3)
