import re, sys
cfg = open("firmware/esp32-diy/include/config.h").read()
doc = open("docs/obd2-dongle/02-wiring.md").read()
label = {5:"D5",4:"D4",18:"D18",21:"D21",22:"D22",15:"D15",17:"TX2",16:"RX2",14:"D14"}
for name in ["CAN_TX_PIN","CAN_RX_PIN","CAN_STBY_PIN","I2C_SDA_PIN","I2C_SCL_PIN","ACC_PIN","GPS_TX_PIN","GPS_RX_PIN","GPS_PWR_PIN"]:
    m = re.search(rf"#define {name}\s+(\d+)", cfg)
    pin = int(m.group(1))
    lab = f"**{label[pin]}**"
    assert f"GPIO {pin}" in doc and lab in doc, f"{name}: GPIO {pin}/{label[pin]} missing from doc"
print("pin map <-> board labels OK:", len(label), "pins")
