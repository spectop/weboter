"""
MQTT 插件 - 提供常见 MQTT 动作

包含：
  - MqttPublish        发布消息（支持 JSON / 字符串）
  - MqttSubscribeOnce  订阅并等待一条消息
  - MqttRequestReply   向请求主题发布并等待响应主题回包
  - MqttCheckConnection 连接探活

依赖：
  - paho-mqtt
"""

from __future__ import annotations

import json
import random
import threading
import time
from typing import Any

from weboter.public.contracts.action import ActionBase
from weboter.public.contracts.interface import InputFieldDeclaration, OutputFieldDeclaration
from weboter.public.contracts.io_pipe import IOPipe


def _load_mqtt_client_module():
    try:
        import paho.mqtt.client as mqtt  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("缺少依赖 paho-mqtt，请先安装：pip install paho-mqtt") from exc
    return mqtt


def _build_client_id(prefix: str = "weboter") -> str:
    ts = int(time.time() * 1000)
    rnd = random.randint(1000, 9999)
    return f"{prefix}_{ts}_{rnd}"


def _parse_broker_inputs(io_inputs: dict[str, Any]) -> dict[str, Any]:
    host = str(io_inputs.get("host") or "").strip()
    if not host:
        raise ValueError("host 不能为空")

    port = int(io_inputs.get("port") or 1883)
    keepalive = int(io_inputs.get("keepalive") or 60)
    connect_timeout = float(io_inputs.get("connect_timeout") or 6)
    wait_timeout = float(io_inputs.get("wait_timeout") or 8)

    return {
        "host": host,
        "port": port,
        "username": str(io_inputs.get("username") or "") or None,
        "password": str(io_inputs.get("password") or "") or None,
        "client_id": str(io_inputs.get("client_id") or "") or _build_client_id("weboter_mqtt"),
        "keepalive": keepalive,
        "connect_timeout": connect_timeout,
        "wait_timeout": wait_timeout,
        "clean_session": bool(io_inputs.get("clean_session") if "clean_session" in io_inputs else True),
        "transport": str(io_inputs.get("transport") or "tcp"),
        "protocol": str(io_inputs.get("protocol") or "v311"),
        "tls": bool(io_inputs.get("tls") or False),
        "tls_insecure": bool(io_inputs.get("tls_insecure") or False),
        "will_topic": str(io_inputs.get("will_topic") or "") or None,
        "will_payload": io_inputs.get("will_payload"),
        "will_qos": int(io_inputs.get("will_qos") or 0),
        "will_retain": bool(io_inputs.get("will_retain") or False),
    }


def _to_payload_bytes(payload: Any, payload_type: str) -> bytes:
    normalized_type = (payload_type or "json").strip().lower()
    if normalized_type == "json":
        text = json.dumps(payload, ensure_ascii=False)
        return text.encode("utf-8")
    if normalized_type == "raw":
        if isinstance(payload, bytes):
            return payload
        return str(payload if payload is not None else "").encode("utf-8")
    raise ValueError(f"不支持的 payload_type: {payload_type}")


def _decode_payload(payload: bytes, payload_encoding: str) -> str:
    encoding = payload_encoding or "utf-8"
    return payload.decode(encoding, errors="replace")


def _maybe_json_loads(text: str) -> Any:
    stripped = text.lstrip()
    if not stripped.startswith("{") and not stripped.startswith("["):
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _create_client(mqtt: Any, options: dict[str, Any]):
    protocol = options.get("protocol") or "v311"
    protocol_map = {
        "v311": mqtt.MQTTv311,
        "v31": mqtt.MQTTv31,
        "v5": mqtt.MQTTv5,
    }
    client = mqtt.Client(
        client_id=options["client_id"],
        clean_session=options["clean_session"],
        protocol=protocol_map.get(protocol, mqtt.MQTTv311),
        transport=options["transport"],
    )

    if options.get("username"):
        client.username_pw_set(options["username"], options.get("password"))

    if options.get("tls"):
        client.tls_set()
        if options.get("tls_insecure"):
            client.tls_insecure_set(True)

    will_topic = options.get("will_topic")
    if will_topic:
        will_payload = options.get("will_payload")
        if isinstance(will_payload, (dict, list)):
            will_payload = json.dumps(will_payload, ensure_ascii=False)
        if will_payload is None:
            will_payload = "offline"
        client.will_set(
            will_topic,
            payload=str(will_payload),
            qos=int(options.get("will_qos") or 0),
            retain=bool(options.get("will_retain") or False),
        )

    return client


class MqttPublish(ActionBase):
    name = "MqttPublish"
    description = "连接 MQTT broker 并发布消息"
    inputs = [
        InputFieldDeclaration(name="host", description="broker 地址", required=True, accepted_types=["string"]),
        InputFieldDeclaration(name="port", description="broker 端口", required=False, accepted_types=["number"], default=1883),
        InputFieldDeclaration(name="username", description="用户名", required=False, accepted_types=["string"], default=""),
        InputFieldDeclaration(name="password", description="密码", required=False, accepted_types=["string"], default=""),
        InputFieldDeclaration(name="topic", description="发布主题", required=True, accepted_types=["string"]),
        InputFieldDeclaration(name="payload", description="消息体（dict/list/string）", required=True, accepted_types=["any"]),
        InputFieldDeclaration(name="payload_type", description="json 或 raw", required=False, accepted_types=["string"], default="json"),
        InputFieldDeclaration(name="qos", description="QoS 级别 0/1/2", required=False, accepted_types=["number"], default=0),
        InputFieldDeclaration(name="retain", description="是否 retain", required=False, accepted_types=["boolean"], default=True),
        InputFieldDeclaration(name="keepalive", description="keepalive 秒", required=False, accepted_types=["number"], default=60),
        InputFieldDeclaration(name="connect_timeout", description="连接超时秒", required=False, accepted_types=["number"], default=6),
        InputFieldDeclaration(name="wait_timeout", description="等待发布完成超时秒", required=False, accepted_types=["number"], default=8),
        InputFieldDeclaration(name="client_id", description="客户端 ID，留空自动生成", required=False, accepted_types=["string"], default=""),
        InputFieldDeclaration(name="clean_session", description="是否 clean session", required=False, accepted_types=["boolean"], default=True),
        InputFieldDeclaration(name="transport", description="tcp 或 websockets", required=False, accepted_types=["string"], default="tcp"),
        InputFieldDeclaration(name="protocol", description="v311/v31/v5", required=False, accepted_types=["string"], default="v311"),
        InputFieldDeclaration(name="tls", description="是否启用 TLS", required=False, accepted_types=["boolean"], default=False),
        InputFieldDeclaration(name="tls_insecure", description="TLS 是否忽略证书校验", required=False, accepted_types=["boolean"], default=False),
        InputFieldDeclaration(name="will_topic", description="遗嘱主题", required=False, accepted_types=["string"], default=""),
        InputFieldDeclaration(name="will_payload", description="遗嘱消息", required=False, accepted_types=["any"], default=None),
        InputFieldDeclaration(name="will_qos", description="遗嘱 QoS", required=False, accepted_types=["number"], default=0),
        InputFieldDeclaration(name="will_retain", description="遗嘱 retain", required=False, accepted_types=["boolean"], default=False),
    ]
    outputs = [
        OutputFieldDeclaration(name="published", description="是否发布成功", type="bool"),
        OutputFieldDeclaration(name="topic", description="实际发布主题", type="string"),
        OutputFieldDeclaration(name="payload_text", description="发布文本", type="string"),
        OutputFieldDeclaration(name="mid", description="消息 ID", type="int"),
    ]

    async def execute(self, io: IOPipe) -> None:
        mqtt = _load_mqtt_client_module()
        options = _parse_broker_inputs(io.inputs)

        topic = str(io.inputs.get("topic") or "").strip()
        if not topic:
            raise ValueError("topic 不能为空")

        qos = int(io.inputs.get("qos") or 0)
        retain = bool(io.inputs.get("retain") if "retain" in io.inputs else True)
        payload_type = str(io.inputs.get("payload_type") or "json")
        payload_bytes = _to_payload_bytes(io.inputs.get("payload"), payload_type)

        connect_event = threading.Event()
        publish_event = threading.Event()
        errors: list[str] = []
        result_mid = 0

        client = _create_client(mqtt, options)

        def on_connect(_client, _userdata, rc, _properties=None):  # pragma: no cover
            if rc != 0:
                errors.append(f"MQTT 连接失败，rc={rc}")
            connect_event.set()

        def on_publish(_client, _userdata, mid):  # pragma: no cover
            nonlocal result_mid
            result_mid = int(mid)
            publish_event.set()

        client.on_connect = on_connect
        client.on_publish = on_publish

        try:
            client.connect(options["host"], options["port"], options["keepalive"])
            client.loop_start()

            if not connect_event.wait(options["connect_timeout"]):
                raise TimeoutError("MQTT 连接超时")
            if errors:
                raise RuntimeError(errors[0])

            info = client.publish(topic, payload=payload_bytes, qos=qos, retain=retain)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"MQTT 发布失败，rc={info.rc}")

            if qos > 0:
                if not publish_event.wait(options["wait_timeout"]):
                    raise TimeoutError("等待 MQTT 发布确认超时")
            else:
                result_mid = int(info.mid)

            payload_text = payload_bytes.decode("utf-8", errors="replace")
            io.outputs["published"] = True
            io.outputs["topic"] = topic
            io.outputs["payload_text"] = payload_text
            io.outputs["mid"] = result_mid
        finally:
            try:
                client.loop_stop()
            finally:
                client.disconnect()


class MqttSubscribeOnce(ActionBase):
    name = "MqttSubscribeOnce"
    description = "订阅主题并等待一条消息后返回"
    inputs = [
        InputFieldDeclaration(name="host", description="broker 地址", required=True, accepted_types=["string"]),
        InputFieldDeclaration(name="port", description="broker 端口", required=False, accepted_types=["number"], default=1883),
        InputFieldDeclaration(name="username", description="用户名", required=False, accepted_types=["string"], default=""),
        InputFieldDeclaration(name="password", description="密码", required=False, accepted_types=["string"], default=""),
        InputFieldDeclaration(name="topic", description="订阅主题，支持通配符", required=True, accepted_types=["string"]),
        InputFieldDeclaration(name="qos", description="订阅 QoS", required=False, accepted_types=["number"], default=0),
        InputFieldDeclaration(name="wait_timeout", description="等待消息超时秒", required=False, accepted_types=["number"], default=15),
        InputFieldDeclaration(name="payload_encoding", description="消息解码编码", required=False, accepted_types=["string"], default="utf-8"),
        InputFieldDeclaration(name="keepalive", description="keepalive 秒", required=False, accepted_types=["number"], default=60),
        InputFieldDeclaration(name="connect_timeout", description="连接超时秒", required=False, accepted_types=["number"], default=6),
        InputFieldDeclaration(name="client_id", description="客户端 ID，留空自动生成", required=False, accepted_types=["string"], default=""),
        InputFieldDeclaration(name="clean_session", description="是否 clean session", required=False, accepted_types=["boolean"], default=True),
        InputFieldDeclaration(name="transport", description="tcp 或 websockets", required=False, accepted_types=["string"], default="tcp"),
        InputFieldDeclaration(name="protocol", description="v311/v31/v5", required=False, accepted_types=["string"], default="v311"),
        InputFieldDeclaration(name="tls", description="是否启用 TLS", required=False, accepted_types=["boolean"], default=False),
        InputFieldDeclaration(name="tls_insecure", description="TLS 是否忽略证书校验", required=False, accepted_types=["boolean"], default=False),
    ]
    outputs = [
        OutputFieldDeclaration(name="received", description="是否收到消息", type="bool"),
        OutputFieldDeclaration(name="topic", description="消息主题", type="string"),
        OutputFieldDeclaration(name="payload_text", description="消息文本", type="string"),
        OutputFieldDeclaration(name="payload_json", description="解析后的 JSON（若可解析）", type="any"),
        OutputFieldDeclaration(name="qos", description="消息 QoS", type="int"),
        OutputFieldDeclaration(name="retain", description="消息 retain", type="bool"),
    ]

    async def execute(self, io: IOPipe) -> None:
        mqtt = _load_mqtt_client_module()
        options = _parse_broker_inputs(io.inputs)

        topic = str(io.inputs.get("topic") or "").strip()
        if not topic:
            raise ValueError("topic 不能为空")

        sub_qos = int(io.inputs.get("qos") or 0)
        payload_encoding = str(io.inputs.get("payload_encoding") or "utf-8")

        connect_event = threading.Event()
        message_event = threading.Event()
        errors: list[str] = []
        message_holder: dict[str, Any] = {}

        client = _create_client(mqtt, options)

        def on_connect(_client, _userdata, rc, _properties=None):  # pragma: no cover
            if rc != 0:
                errors.append(f"MQTT 连接失败，rc={rc}")
            else:
                client.subscribe(topic, qos=sub_qos)
            connect_event.set()

        def on_message(_client, _userdata, msg):  # pragma: no cover
            text = _decode_payload(msg.payload, payload_encoding)
            message_holder["topic"] = msg.topic
            message_holder["payload_text"] = text
            message_holder["payload_json"] = _maybe_json_loads(text)
            message_holder["qos"] = int(getattr(msg, "qos", 0))
            message_holder["retain"] = bool(getattr(msg, "retain", False))
            message_event.set()

        client.on_connect = on_connect
        client.on_message = on_message

        try:
            client.connect(options["host"], options["port"], options["keepalive"])
            client.loop_start()

            if not connect_event.wait(options["connect_timeout"]):
                raise TimeoutError("MQTT 连接超时")
            if errors:
                raise RuntimeError(errors[0])

            if not message_event.wait(options["wait_timeout"]):
                raise TimeoutError("等待 MQTT 消息超时")

            io.outputs["received"] = True
            io.outputs["topic"] = message_holder.get("topic", "")
            io.outputs["payload_text"] = message_holder.get("payload_text", "")
            io.outputs["payload_json"] = message_holder.get("payload_json")
            io.outputs["qos"] = int(message_holder.get("qos", 0))
            io.outputs["retain"] = bool(message_holder.get("retain", False))
        finally:
            try:
                client.loop_stop()
            finally:
                client.disconnect()


class MqttRequestReply(ActionBase):
    name = "MqttRequestReply"
    description = "向 request_topic 发布请求并等待 reply_topic 响应"
    inputs = [
        InputFieldDeclaration(name="host", description="broker 地址", required=True, accepted_types=["string"]),
        InputFieldDeclaration(name="port", description="broker 端口", required=False, accepted_types=["number"], default=1883),
        InputFieldDeclaration(name="username", description="用户名", required=False, accepted_types=["string"], default=""),
        InputFieldDeclaration(name="password", description="密码", required=False, accepted_types=["string"], default=""),
        InputFieldDeclaration(name="request_topic", description="请求主题", required=True, accepted_types=["string"]),
        InputFieldDeclaration(name="reply_topic", description="响应主题（可含通配符）", required=True, accepted_types=["string"]),
        InputFieldDeclaration(name="payload", description="请求消息体", required=True, accepted_types=["any"]),
        InputFieldDeclaration(name="payload_type", description="json 或 raw", required=False, accepted_types=["string"], default="json"),
        InputFieldDeclaration(name="request_qos", description="请求 QoS", required=False, accepted_types=["number"], default=0),
        InputFieldDeclaration(name="reply_qos", description="订阅响应 QoS", required=False, accepted_types=["number"], default=0),
        InputFieldDeclaration(name="retain", description="请求是否 retain", required=False, accepted_types=["boolean"], default=False),
        InputFieldDeclaration(name="wait_timeout", description="等待响应超时秒", required=False, accepted_types=["number"], default=15),
        InputFieldDeclaration(name="payload_encoding", description="响应解码编码", required=False, accepted_types=["string"], default="utf-8"),
        InputFieldDeclaration(name="keepalive", description="keepalive 秒", required=False, accepted_types=["number"], default=60),
        InputFieldDeclaration(name="connect_timeout", description="连接超时秒", required=False, accepted_types=["number"], default=6),
        InputFieldDeclaration(name="client_id", description="客户端 ID，留空自动生成", required=False, accepted_types=["string"], default=""),
        InputFieldDeclaration(name="clean_session", description="是否 clean session", required=False, accepted_types=["boolean"], default=True),
        InputFieldDeclaration(name="transport", description="tcp 或 websockets", required=False, accepted_types=["string"], default="tcp"),
        InputFieldDeclaration(name="protocol", description="v311/v31/v5", required=False, accepted_types=["string"], default="v311"),
        InputFieldDeclaration(name="tls", description="是否启用 TLS", required=False, accepted_types=["boolean"], default=False),
        InputFieldDeclaration(name="tls_insecure", description="TLS 是否忽略证书校验", required=False, accepted_types=["boolean"], default=False),
    ]
    outputs = [
        OutputFieldDeclaration(name="ok", description="是否收到响应", type="bool"),
        OutputFieldDeclaration(name="request_topic", description="请求主题", type="string"),
        OutputFieldDeclaration(name="reply_topic", description="响应主题", type="string"),
        OutputFieldDeclaration(name="reply_payload_text", description="响应文本", type="string"),
        OutputFieldDeclaration(name="reply_payload_json", description="响应 JSON（若可解析）", type="any"),
    ]

    async def execute(self, io: IOPipe) -> None:
        mqtt = _load_mqtt_client_module()
        options = _parse_broker_inputs(io.inputs)

        request_topic = str(io.inputs.get("request_topic") or "").strip()
        reply_topic = str(io.inputs.get("reply_topic") or "").strip()
        if not request_topic or not reply_topic:
            raise ValueError("request_topic 与 reply_topic 均不能为空")

        payload_type = str(io.inputs.get("payload_type") or "json")
        payload_bytes = _to_payload_bytes(io.inputs.get("payload"), payload_type)
        request_qos = int(io.inputs.get("request_qos") or 0)
        reply_qos = int(io.inputs.get("reply_qos") or 0)
        retain = bool(io.inputs.get("retain") or False)
        payload_encoding = str(io.inputs.get("payload_encoding") or "utf-8")

        connect_event = threading.Event()
        message_event = threading.Event()
        errors: list[str] = []
        message_holder: dict[str, Any] = {}

        client = _create_client(mqtt, options)

        def on_connect(_client, _userdata, rc, _properties=None):  # pragma: no cover
            if rc != 0:
                errors.append(f"MQTT 连接失败，rc={rc}")
            else:
                client.subscribe(reply_topic, qos=reply_qos)
                info = client.publish(request_topic, payload=payload_bytes, qos=request_qos, retain=retain)
                if info.rc != mqtt.MQTT_ERR_SUCCESS:
                    errors.append(f"MQTT 发布失败，rc={info.rc}")
            connect_event.set()

        def on_message(_client, _userdata, msg):  # pragma: no cover
            text = _decode_payload(msg.payload, payload_encoding)
            message_holder["reply_topic"] = msg.topic
            message_holder["reply_payload_text"] = text
            message_holder["reply_payload_json"] = _maybe_json_loads(text)
            message_event.set()

        client.on_connect = on_connect
        client.on_message = on_message

        try:
            client.connect(options["host"], options["port"], options["keepalive"])
            client.loop_start()

            if not connect_event.wait(options["connect_timeout"]):
                raise TimeoutError("MQTT 连接超时")
            if errors:
                raise RuntimeError(errors[0])

            if not message_event.wait(options["wait_timeout"]):
                raise TimeoutError("等待 MQTT 响应超时")

            io.outputs["ok"] = True
            io.outputs["request_topic"] = request_topic
            io.outputs["reply_topic"] = message_holder.get("reply_topic", "")
            io.outputs["reply_payload_text"] = message_holder.get("reply_payload_text", "")
            io.outputs["reply_payload_json"] = message_holder.get("reply_payload_json")
        finally:
            try:
                client.loop_stop()
            finally:
                client.disconnect()


class MqttCheckConnection(ActionBase):
    name = "MqttCheckConnection"
    description = "检查 MQTT broker 可连接性"
    inputs = [
        InputFieldDeclaration(name="host", description="broker 地址", required=True, accepted_types=["string"]),
        InputFieldDeclaration(name="port", description="broker 端口", required=False, accepted_types=["number"], default=1883),
        InputFieldDeclaration(name="username", description="用户名", required=False, accepted_types=["string"], default=""),
        InputFieldDeclaration(name="password", description="密码", required=False, accepted_types=["string"], default=""),
        InputFieldDeclaration(name="keepalive", description="keepalive 秒", required=False, accepted_types=["number"], default=60),
        InputFieldDeclaration(name="connect_timeout", description="连接超时秒", required=False, accepted_types=["number"], default=6),
        InputFieldDeclaration(name="client_id", description="客户端 ID，留空自动生成", required=False, accepted_types=["string"], default=""),
        InputFieldDeclaration(name="clean_session", description="是否 clean session", required=False, accepted_types=["boolean"], default=True),
        InputFieldDeclaration(name="transport", description="tcp 或 websockets", required=False, accepted_types=["string"], default="tcp"),
        InputFieldDeclaration(name="protocol", description="v311/v31/v5", required=False, accepted_types=["string"], default="v311"),
        InputFieldDeclaration(name="tls", description="是否启用 TLS", required=False, accepted_types=["boolean"], default=False),
        InputFieldDeclaration(name="tls_insecure", description="TLS 是否忽略证书校验", required=False, accepted_types=["boolean"], default=False),
    ]
    outputs = [
        OutputFieldDeclaration(name="ok", description="是否连通", type="bool"),
        OutputFieldDeclaration(name="host", description="broker 地址", type="string"),
        OutputFieldDeclaration(name="port", description="broker 端口", type="int"),
        OutputFieldDeclaration(name="message", description="结果信息", type="string"),
    ]

    async def execute(self, io: IOPipe) -> None:
        mqtt = _load_mqtt_client_module()
        options = _parse_broker_inputs(io.inputs)

        connect_event = threading.Event()
        result = {"ok": False, "message": ""}

        client = _create_client(mqtt, options)

        def on_connect(_client, _userdata, rc, _properties=None):  # pragma: no cover
            if rc == 0:
                result["ok"] = True
                result["message"] = "connected"
            else:
                result["ok"] = False
                result["message"] = f"connect_failed_rc_{rc}"
            connect_event.set()

        client.on_connect = on_connect

        try:
            client.connect(options["host"], options["port"], options["keepalive"])
            client.loop_start()
            if not connect_event.wait(options["connect_timeout"]):
                raise TimeoutError("MQTT 连接超时")
            io.outputs["ok"] = bool(result["ok"])
            io.outputs["host"] = options["host"]
            io.outputs["port"] = int(options["port"])
            io.outputs["message"] = str(result["message"])
        finally:
            try:
                client.loop_stop()
            finally:
                client.disconnect()
