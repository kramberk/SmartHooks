import network
import espnow
from machine import Pin, SPI, I2C
from time import sleep
from hcsr04 import HCSR04
import ssd1306
from mfrc522 import MFRC522

ENABLE_CHANNEL_FIND = 0

#### RFID CONFIGURATION SECTION

# Pin configuration
SCK_PIN  = 5
MOSI_PIN = 19
MISO_PIN = 21
RST_PIN  = 27
CS_PIN   = 22

# SPI setup
spi = SPI(
    2,
    baudrate=2500000,
    polarity=0,
    phase=0,
    sck=Pin(SCK_PIN),
    mosi=Pin(MOSI_PIN),
    miso=Pin(MISO_PIN)
)

# RFID module setup
rfid = MFRC522(
    spi=spi,
    gpioRst=Pin(RST_PIN),
    gpioCs=Pin(CS_PIN)
)

# Authorized card UID
AUTHORIZED_UID = "786E5C3E"

# RFID status variable
rfidbool = 0

print("RC522 RFID reader ready. Bring a card close...")



#### OLED setup

SCL_PIN = 32
SDA_PIN = 15
OLED_WIDTH = 128
OLED_HEIGHT = 32
OLED_ADDRESS = 0x3c  # Standard I2C address for SSD1306

try:
    # Initialize I2C and OLED display
    i2c = I2C(0, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=400000)
    oled = ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c, OLED_ADDRESS)
    oled.fill(0) # Clear display
    print(f"OLED initialized on SCL: {SCL_PIN}, SDA: {SDA_PIN}")
except Exception as e:
    print(f"Error during initialization: {e}")
    print("Check your wiring and I2C address.")
    oled = None


#### Ultrasonic sensor setup
sensor = HCSR04(trigger_pin=7, echo_pin=8, echo_timeout_us=10000)
print("Ultrasonic distance sensor ready. move close to send message.")



#### ESP WiFi COMM Section
# ESP-NOW Sender Setup
CURRENT_CHANNEL = 1

peer = b'\x14\x2b\x2f\xae\xe3\xa4'  # MAC address of peer's wifi interface 142b2faee3a4

sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.disconnect()

e = espnow.ESPNow()
e.active(True)

def find_receiver_channel():
    sleep(2)
    channels = range(1, 14) # Channels 1 to 13
    for channel in channels:
        sta.config(channel=channel)
        print(f"Trying channel {channel}...")
        
        # Add the receiver as a peer on the current channel
        try:
            e.add_peer(peer)
        except OSError:
            # Peer might already be added, which is fine
            pass

        # Send a discovery message (e.g., "PING")
        e.send(peer, b"STARTING")
        
        # Wait briefly for an acknowledgment
        host, msg = e.recv(250) # Timeout after 250ms
        
        if msg == b"RECEIVED":
            print(f"Receiver found on channel {channel}!")
            return channel
        
        # If no acknowledgment, remove the peer for the next channel iteration
        e.del_peer(peer)
        sleep(0.1)

    return 1

if ENABLE_CHANNEL_FIND == 1:
    CURRENT_CHANNEL = find_receiver_channel()

sta.config(channel=CURRENT_CHANNEL)
e.add_peer(peer)
e.send(peer, "Starting...")


##### MAIN LOOP
while True:
    distance = sensor.distance_cm()
    print('Distance:', distance, 'cm')
    
    oled.fill(0)
    
    # Read RFID and set up RFID status
    status, tag_type = rfid.request(rfid.REQIDL)

    if status == rfid.OK:
        print("Card detected, type:", hex(tag_type))

        status, raw_uid = rfid.anticoll()

        
        uid_hex = "%02X%02X%02X%02X" % (
            raw_uid[0],
            raw_uid[1],
            raw_uid[2],
            raw_uid[3]
        )

        print("Card UID:", uid_hex)

        if uid_hex == AUTHORIZED_UID:
            print("Authorized card")
            rfidbool = 1
        else:
            print("Unknown card")
            rfidbool = -1

        rfid.select_tag(raw_uid)
        rfid.stop_crypto1()
        print("------------------------------")
        

        if rfidbool == 1:
            oled.text("Access Granted", 0, 16)
            oled.show()
        elif rfidbool == -1:
            oled.text("Access Denied", 0, 16)
            oled.show()
        else:
            oled.text("Standby", 0, 16)
            oled.show()
        
        try:
            # Build the comm payload : distance,rfidbool
            payload = distance
            combined = f"{payload},{rfidbool}"
            e.send(peer, combined)
        except OSError as err:
            print("ESP-NOW send failed:", err)
    else:
        try:
            # Build the comm payload : distance,rfidbool
            payload = distance
            rfidbool = 0
            combined = f"{payload},{rfidbool}"
            e.send(peer, combined)
            oled.text("Standby", 0, 16)
            oled.show()
        except OSError as err:
            print("ESP-NOW send failed:", err)
       
    sleep(1)


