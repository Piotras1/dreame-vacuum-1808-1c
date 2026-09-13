> ⚠️ **IMPORTANT DISCLAIMER**
> This integration is **exclusively designed for the Dreame MC1808 / Xiaomi Mi Robot Vacuum-Mop 1C (STYTJ01ZHM)** model. It will **NOT** work with other Dreame or Xiaomi vacuum models.

# Dreame Vacuum MC1808 / Xiaomi Mi Robot Vacuum-Mop 1C Custom Component

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/Piotras1/dreame-vacuum-1808-1c)](https://github.com/Piotras1/dreame-vacuum-1808-1c/releases)
[![Maintainer](https://img.shields.io/badge/maintainer-Piotr%20%28%40Piotras1%29-blue)](https://github.com/Piotras1)

Custom Home Assistant integration for **Dreame MC1808** (sold also as **Xiaomi Mi Robot Vacuum-Mop 1C** / `STYTJ01ZHM`). 

This component offers a modern, fully UI-configurable (Config Flow) integration built natively for recent Home Assistant releases, replacing legacy YAML configurations with zero external daemon dependencies.

---

## Features

* **UI Configuration (Config Flow):** Easy setup via the Home Assistant frontend using host IP and local 32-character miIO token.
* **Vacuum Controls:** Start, pause, stop, return to dock, and set fan speeds (Silent, Standard, Strong, Turbo).
* **Zone Cleaning:** Built-in `dreame_mc1808.vacuum_clean_zone` service support.
* **Sensors:** Monitor battery level, current status, filter life, main/side brush life, total cleaning area, and cleaning time.
* **Diagnostic Sensors:** Direct tracking of active state binary sensors and hardware telemetry.
* **Pure Python Client:** Native encryption and payload parser built directly into the integration (`construct` & `cryptography`).

<img width="1158" height="846" alt="Zrzut ekranu (2585)" src="https://github.com/user-attachments/assets/65c15e10-2ae4-4aeb-956a-42a6f2ae3bc2" />

---

## Quick Installation via HACS

Click the button below to open this repository directly inside your Home Assistant Community Store (HACS):

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Piotras1&repository=dreame-vacuum-1808-1c&category=integration)

### Manual HACS Setup
1. Open **HACS** in your Home Assistant instance.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Paste the URL: `https://github.com/Piotras1/dreame-vacuum-1808-1c`
4. Select **Integration** as the category and click **Add**.
5. Find **Dreame Vacuum ( MC1808 )** in HACS and click **Download**.
6. **Restart Home Assistant**.

---

## Manual Installation

1. Download the latest release `.zip` archive from the Releases page.
2. Extract and copy the `custom_components/dreame_mc1808` directory to your Home Assistant's `config/custom_components/` folder.
3. **Restart Home Assistant**.

---

## Configuration

1. Go to **Settings** -> **Devices & Services**.
2. Click **Add Integration** in the bottom right corner.
3. Search for **Dreame Vacuum (MC1808)**.
4. Enter your device details:
   * **Host:** Local IP address of your vacuum cleaner.
   * **Token:** 32-character local device token.
   * **Name:** Custom name for the vacuum (defaults to `Dreame Vacuum`).
5. Click **Submit**.

<img width="565" height="170" alt="Zrzut ekranu (2583)" src="https://github.com/user-attachments/assets/8fb4f85f-db7b-4e49-9061-277780ebca3f" />
   
---

## Available Services

### `dreame_mc1808.vacuum_clean_zone`
Sends the vacuum cleaner to clean specific rectangular zones.

**Service Data Payload:**
```yaml
service: dreame_mc1808.vacuum_clean_zone
target:
  entity_id: vacuum.tadeusz
data:
  zone: "-4650,-6450,-2000,-4750"
  repeats: 1
```

## Supported Devices
- Dreame MC1808
- Xiaomi Mi Robot Vacuum-Mop 1C (STYTJ01ZHM)

## License
Distributed under the MIT License. See LICENSE for more information.

---
*Created by Piotras. Strictly engineered for reliability.*
