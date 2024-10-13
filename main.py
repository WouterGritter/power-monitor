import os
from datetime import datetime
from enum import IntEnum

import paho.mqtt.client as mqtt
from discord_webhook import DiscordWebhook

MQTT_BROKER_ADDRESS = os.getenv('MQTT_BROKER_ADDRESS', 'localhost')
MQTT_BROKER_PORT = int(os.getenv('MQTT_BROKER_PORT', '1883'))
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
TOPIC_FORMAT = os.getenv('TOPIC_FORMAT')
WARNING_AMPERAGE = float(os.getenv('WARNING_AMPERAGE'))
CRITICAL_AMPERAGE = float(os.getenv('CRITICAL_AMPERAGE'))

NUMBER_EMOJIS = [':zero:', ':one:', ':two:', ':three:', ':four:', ':five:', ':six:', ':seven:', ':eight:', ':nine:', ':keycap_ten:']
NUMBER_NAMES = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']


class AlertLevel(IntEnum):
    NOMINAL = (1, '🟢', None)
    WARNING = (2, '🟠', 60)
    CRITICAL = (3, '🔴', 5)

    def __new__(cls, value, emoji, repeat_interval):
        obj = int.__new__(cls, value)
        obj._value_ = value

        obj.emoji = emoji
        obj.repeat_interval = repeat_interval

        return obj


class PhaseDaemon:
    def __init__(self, phase: int, warning_threshold: float, critical_threshold: float):
        self.phase = phase
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold

        self.topic = TOPIC_FORMAT.format(phase=phase)

        self.alert_level = AlertLevel.NOMINAL
        self.last_alert_repeat = datetime.now()

    def subscribe(self, client):
        client.subscribe(self.topic)

    def on_reading(self, amperage: float):
        new_alert_level = self.calculate_alert_level(amperage)

        if new_alert_level != self.alert_level:
            # Alert level has changed
            self.on_alert_level_change(self.alert_level, new_alert_level, amperage)
            self.alert_level = new_alert_level

            self.last_alert_repeat = datetime.now()
        else:
            # Alert level has not changed
            if self.alert_level.repeat_interval is not None:
                time_since_last_alert = (datetime.now() - self.last_alert_repeat).total_seconds()
                if time_since_last_alert > self.alert_level.repeat_interval:
                    self.on_alert_repeat(new_alert_level, amperage)
                    self.last_alert_repeat = datetime.now()

    def on_alert_level_change(self, old_level: AlertLevel, new_level: AlertLevel, amperage: float):
        if new_level > old_level:
            send_discord_message(f'Phase **{NUMBER_NAMES[self.phase].upper()}** increased :arrow_up: alert level to **{new_level.name}** {new_level.emoji} (`{amperage:.1f} A`) {":warning:" if new_level == AlertLevel.CRITICAL else ""}')
        else:
            send_discord_message(f'Phase **{NUMBER_NAMES[self.phase].upper()}** decreased :arrow_down: alert level to {new_level.name} {new_level.emoji} (`{amperage:.1f} A`)')

    def on_alert_repeat(self, alert_level: AlertLevel, amperage: float):
        send_discord_message(f'Phase **{NUMBER_NAMES[self.phase].upper()}** alert level is still **{alert_level.name}** {alert_level.emoji} (`{amperage:.1f} A`)')

    def calculate_alert_level(self, amperage: float):
        if amperage > self.critical_threshold:
            return AlertLevel.CRITICAL
        elif amperage > self.warning_threshold:
            return AlertLevel.WARNING
        else:
            return AlertLevel.NOMINAL


phases = [
    PhaseDaemon(phase + 1, WARNING_AMPERAGE, CRITICAL_AMPERAGE)
    for phase in range(3)
]


def send_discord_message(message: str):
    print(message)
    DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=message).execute()


def on_connect(client, userdata, flags, reason_code, properties):
    print('Connected to MQTT.')

    for phase in phases:
        phase.subscribe(client)


def on_message(client, userdata, msg):
    payload = float(msg.payload.decode('utf-8'))

    for phase in phases:
        if phase.topic == msg.topic:
            phase.on_reading(payload)


def main():
    print(f'power-warning version {os.getenv("IMAGE_VERSION")}')

    print(f'{MQTT_BROKER_ADDRESS=}')
    print(f'{MQTT_BROKER_PORT=}')
    print(f'{DISCORD_WEBHOOK_URL=}')
    print(f'{TOPIC_FORMAT=}')
    print(f'{WARNING_AMPERAGE=}')
    print(f'{CRITICAL_AMPERAGE=}')

    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqttc.on_connect = on_connect
    mqttc.on_message = on_message

    mqttc.connect(MQTT_BROKER_ADDRESS, MQTT_BROKER_PORT, 60)
    mqttc.loop_forever()


if __name__ == '__main__':
    main()
