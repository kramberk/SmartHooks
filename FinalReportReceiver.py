import network
import espnow
from machine import Pin, PWM, ADC
from time import sleep
import utime
import json
import urequests

ENABLE_DISCORD = 1
ENABLE_CHANNEL_FIND = 1

sta = None  # For debugging - keep global reference to STA

#LED
led = Pin(13, Pin.OUT)
led.value(0)

#### Servo section

# Servo configuration
p5 = Pin(5, Pin.OUT, value=0)
p19 = Pin(19, Pin.OUT, value=0)
p21 = Pin(21, Pin.OUT, value=0)
servo1 = PWM(p5, freq=50)
servo2 = PWM(p19, freq=50)
servo3 = PWM(p21, freq=50)


# Servo control methods
def set_angle(servoObj, angle):
    min_duty = 26
    max_duty = 123
    angle = max(0, min(180, angle))
    duty = int(min_duty + (angle / 180) * (max_duty - min_duty))
    print("Angle:", angle, "deg | Duty:", duty)
    servoObj.duty(duty)


def rotate_servo_open(servoObj):
    set_angle(servoObj, 180)


def rotate_servo_close(servoObj):
    set_angle(servoObj, 0)


print("Servo motors configured and ready...")


#### Force sensors section

# Configuring the ADC pins (GPIO 34, 33, and 32) for reading force sensors
adc1 = ADC(Pin(34))
adc1.atten(ADC.ATTN_11DB)   # 0-3.3V
adc1.width(ADC.WIDTH_12BIT)

adc2 = ADC(Pin(33))
adc2.atten(ADC.ATTN_11DB)
adc2.width(ADC.WIDTH_12BIT)

adc3 = ADC(Pin(32))
adc3.atten(ADC.ATTN_11DB)
adc3.width(ADC.WIDTH_12BIT)

print("Reading Force Sensitive Resistors...")


#### Configure WiFi for Discord logging of RFID tag use
SSID = "xxxx"
PASSWORD = 'xxxx'
WEBHOOK_URL = "xxxx"
CURRENT_CHANNEL = 1


def connect_to_wifi(ssid, password):
    #Connects to the Wi-Fi network
    sta = network.WLAN(network.STA_IF)
    if not sta.isconnected():
        print('Connecting to Wi-Fi...')
        sta.active(True)
        sta.connect(ssid, password)
        while not sta.isconnected():
            utime.sleep(0.5)
            print(".", end="")
        print("\nConnected to Wi-Fi")
    #For debugging
    print("After connect_to_wifi:")
    print("  active:", sta.active())
    print("  isconnected:", sta.isconnected())
    print("  ifconfig:", sta.ifconfig())
    return sta


def send_discord_notification(message):
    #For debugging - print Wi-Fi status before trying
    wlan = network.WLAN(network.STA_IF)
    print("send_discord_notification() called with:", message)
    print("  STA active:", wlan.active(), "isconnected:", wlan.isconnected())

    if not wlan.isconnected():
        print("Wi-Fi not connected. Skipping Discord send.")
        return

    try:
        payload = {"content": message}
        headers = {"Content-Type": "application/json"}

        print("Posting to Discord...")
        response = urequests.post(
            WEBHOOK_URL,
            data=json.dumps(payload),
            headers=headers,
        )

        print("HTTP Response code:", response.status_code)
        # read small part of body
        try:
            body = response.text
            print("Response body (first 100 chars):", body[:100])
        except Exception as e:
            print("Could not read response body:", e)

        response.close()

    except Exception as e:
        import sys
        print("Error sending message:")
        sys.print_exception(e)


#### ESP WiFi COMM Section
# ESP-NOW Receiver Setup


def confirm_receiver_channel():
    while True:
        host, msg = e.recv(10000)  # timeout in 10 seconds
        if host:
            print("Received discovery message from", host, "on current channel")
            try:
                e.add_peer(host)
                e.send(host, b"RECEIVED")
                break  # Exit the loop once communication is established
            except OSError as err:
                print("Failed to add peer:", err)
        else:
            print("Failed to get discovery message and getting out")


if ENABLE_DISCORD == 0:
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    sta.disconnect()
    sta.config(channel=CURRENT_CHANNEL)
    e = espnow.ESPNow()
    e.active(True)
else:
    sta = connect_to_wifi(SSID, PASSWORD)
    e = espnow.ESPNow()
    e.active(True)
    if ENABLE_CHANNEL_FIND == 1:
        confirm_receiver_channel()

print("WiFi receiver ready. Waiting for distance messages...")


# For periodic Wi-Fi status debug
last_wifi_check = utime.ticks_ms()

while True:
    host, msg = e.irecv(100)  # Wait up to 0.1 second

    #For debugging - every 5 seconds, print Wi-Fi status
    if utime.ticks_diff(utime.ticks_ms(), last_wifi_check) > 5000:
        wlan = network.WLAN(network.STA_IF)
        print(
            "WiFi check -> active:",
            wlan.active(),
            "connected:",
            wlan.isconnected(),
            "ifconfig:",
            wlan.ifconfig(),
        )
        last_wifi_check = utime.ticks_ms()

    if msg:
        try:
            message_str = msg.decode("utf-8")
            print("Received from", host, ":", message_str)
            str_list = message_str.split(",")
            if len(str_list) >= 2:
                dist_value = float(str_list[0])
                message_rfid = float(str_list[1])
                print(
                    "Distance received:",
                    dist_value,
                    "cm; RFID status:",
                    message_rfid,
                )
            else:
                dist_value = -1
                message_rfid = 0
                print("Distance reset:", dist_value, "cm; RFID status:", message_rfid)
            
            force_value1 = adc1.read()
            force_value2 = adc2.read()
            force_value3 = adc3.read()
            print("FSR readings:", force_value1, force_value2, force_value3)

            # Person detection logic
            if dist_value > 30 or dist_value <= 0:
                rotate_servo_open(servo1)
                rotate_servo_open(servo2)
                rotate_servo_close(servo3)

            elif dist_value > 0 and dist_value <= 30:

                if force_value1 <= 10000:
                    rotate_servo_close(servo1)

                if force_value2 <= 500:
                    rotate_servo_close(servo2)

                if force_value3 <= 500:
                    rotate_servo_open(servo3)
            
            if force_value2 >= 500 and force_value3 >= 500:
                led.value(0)
            else:
                led.value(1)

            # RFID detect logic
            if message_rfid == 1:
                print("RFID: authorized, opening + (maybe) sending Discord")
                rotate_servo_close(servo1)
                rotate_servo_close(servo2)
                rotate_servo_open(servo3)
                sleep(5)
                rotate_servo_open(servo1)
                rotate_servo_open(servo2)
                rotate_servo_close(servo3)
                if ENABLE_DISCORD == 1:
                    send_discord_notification("Authorized card")

            elif message_rfid == -1:
                print("RFID: unknown card")
                if ENABLE_DISCORD == 1:
                    send_discord_notification("Unknown card")

        except Exception as err:
            print("Error decoding message:", err)


