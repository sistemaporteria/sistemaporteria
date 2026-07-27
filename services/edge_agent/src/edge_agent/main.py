"""Entry point: subscribe to Frigate over MQTT, emit access events.

python -m edge_agent                      # run against the broker
python -m edge_agent --replay events.jsonl  # replay recorded messages, no broker needed
python -m edge_agent --status               # outbox counters
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
import time
from pathlib import Path

from .config import Config
from .frigate import parse_event, parse_tracked_object_update
from .models import AccessEvent
from .outbox import Outbox
from .pipeline import Pipeline
from .transport import Synchronizer, build_sink

logger = logging.getLogger("edge_agent")

SYNC_INTERVAL_SECONDS = 10
PRUNE_INTERVAL_SECONDS = 300


def build_pipeline(config: Config, outbox: Outbox) -> Pipeline:
  def emit(event: AccessEvent) -> None:
    queued = outbox.enqueue(event.frigate_event_id, event.to_payload())
    logger.info(
      "%s %s placa=%s conf=%.2f veredicto=%s revision=%s%s",
      event.camera_id,
      event.direction.value,
      event.plate_read or "-",
      event.ocr_confidence or 0.0,
      event.verdict.value,
      event.needs_review,
      "" if queued else " (duplicado, ya en cola)",
    )

  return Pipeline(config, emit)


def run_replay(config: Config, path: Path, sync: bool = False) -> int:
  """Feed recorded MQTT messages through the pipeline.

  Each line is `{"topic": "...", "payload": {...}}`. This is what makes the agent testable
  without a broker, a camera or Frigate. With --sync it also drains the outbox, exercising
  the whole chain down to the database.
  """
  outbox = Outbox(config.outbox_path)
  pipeline = build_pipeline(config, outbox)
  processed = 0

  for line in path.read_text(encoding="utf-8-sig").splitlines():
    line = line.strip()
    if not line:
      continue
    record = json.loads(line)
    topic = record.get("topic", "")
    payload = json.dumps(record.get("payload"))
    _dispatch(pipeline, config, topic, payload)
    processed += 1

  logger.info("reproducidos %d mensajes", processed)
  logger.info("outbox: %s", outbox.counts())

  if sync:
    delivered, failed = Synchronizer(outbox, build_sink(config)).drain()
    logger.info("sincronizados %d, fallidos %d", delivered, failed)
    logger.info("outbox: %s", outbox.counts())
  return 0


def _dispatch(pipeline: Pipeline, config: Config, topic: str, payload: str) -> None:
  prefix = config.mqtt_topic_prefix
  if topic == f"{prefix}/events":
    message = parse_event(payload)
    if message:
      pipeline.handle_event(message)
  elif topic == f"{prefix}/tracked_object_update":
    message = parse_tracked_object_update(payload)
    if message:
      pipeline.handle_lpr(message)


def _background_loop(
  synchronizer: Synchronizer, pipeline: Pipeline, stopping: threading.Event
) -> None:
  """Drain the outbox and drop stale objects, on a timer, off the MQTT thread."""
  last_prune = time.monotonic()
  while not stopping.wait(SYNC_INTERVAL_SECONDS):
    delivered, failed = synchronizer.drain()
    if delivered or failed:
      logger.info("sincronizados %d, fallidos %d", delivered, failed)
    stuck = synchronizer.stuck()
    if stuck:
      logger.error("%d eventos atascados tras agotar reintentos: %s", len(stuck), stuck[:5])
    if time.monotonic() - last_prune > PRUNE_INTERVAL_SECONDS:
      pipeline.prune()
      last_prune = time.monotonic()


def run_mqtt(config: Config) -> int:
  try:
    import paho.mqtt.client as mqtt
  except ImportError:
    logger.error("falta paho-mqtt. Instalar con: pip install paho-mqtt")
    return 1

  outbox = Outbox(config.outbox_path)
  pipeline = build_pipeline(config, outbox)
  synchronizer = Synchronizer(outbox, build_sink(config))
  stopping = threading.Event()

  def on_connect(client, _userdata, _flags, reason_code, _properties=None) -> None:
    if reason_code != 0:
      logger.error("conexion MQTT rechazada: %s", reason_code)
      return
    for topic in (
      f"{config.mqtt_topic_prefix}/events",
      f"{config.mqtt_topic_prefix}/tracked_object_update",
    ):
      client.subscribe(topic)
      logger.info("suscrito a %s", topic)

  def on_message(_client, _userdata, message) -> None:
    try:
      _dispatch(pipeline, config, message.topic, message.payload.decode("utf-8"))
    except Exception:  # noqa: BLE001
      # One malformed message must not end the shift.
      logger.exception("fallo procesando %s", message.topic)

  client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
  client.on_connect = on_connect
  client.on_message = on_message

  worker = threading.Thread(
    target=_background_loop,
    args=(synchronizer, pipeline, stopping),
    daemon=True,
    name="sync",
  )
  worker.start()

  def shutdown(_signum, _frame) -> None:
    logger.info("deteniendo...")
    stopping.set()
    client.disconnect()

  signal.signal(signal.SIGINT, shutdown)
  signal.signal(signal.SIGTERM, shutdown)

  logger.info("conectando a mqtt://%s:%d", config.mqtt_host, config.mqtt_port)
  client.connect(config.mqtt_host, config.mqtt_port, keepalive=60)
  client.loop_forever()
  return 0


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--replay", type=Path, help="reproducir mensajes grabados (JSONL)")
  parser.add_argument("--sync", action="store_true", help="con --replay: drenar el outbox")
  parser.add_argument("--status", action="store_true", help="mostrar estado del outbox")
  parser.add_argument("--verbose", action="store_true")
  args = parser.parse_args(argv)

  logging.basicConfig(
    level=logging.DEBUG if args.verbose else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
  )

  config = Config.from_env()

  if args.status:
    print(json.dumps(Outbox(config.outbox_path).counts(), indent=2))
    return 0
  if args.replay:
    return run_replay(config, args.replay, sync=args.sync)
  return run_mqtt(config)


if __name__ == "__main__":
  sys.exit(main())
