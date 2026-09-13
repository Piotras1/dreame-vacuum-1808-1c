> ⚠️ **IMPORTANT DISCLAIMER**
> This integration is **exclusively designed for the Dreame MC1808 / Xiaomi Mi Robot Vacuum-Mop 1C (STYTJ01ZHM)** model. It will **NOT** work with other Dreame or Xiaomi vacuum models.

## About

This custom integration provides **100% working local control** for the **Dreame MC1808 / Xiaomi Mi Robot Vacuum-Mop 1C (STYTJ01ZHM)** in modern versions of Home Assistant.

Unlike older integrations that required manual `configuration.yaml` entries and offered limited functionality, this modern integration is fully configurable via UI and exposes all available diagnostic sensors.

**Key features:**
- Full local control (no cloud needed).
- Easy UI-based setup (Config Flow).
- Real-time battery level and state binary sensors.
- Consumable monitoring (Main brush, Side brush, and Filter life).
- Targeted zone cleaning (via automations).

<p align="center">
  <img src="https://raw.githubusercontent.com/Piotras1/dreame-vacuum-1808-1c/main/images/device_panel.png" alt="Dreame MC1808 Device Panel in Home Assistant">
</p>

## Installation

### Manual Installation

1. Download the repository source code or release archive.
2. Extract and copy the `dreame_mc1808` folder into your Home Assistant's `custom_components` directory:
   ```text
   config/custom_components/dreame_mc1808/
3.   Restart Home Assistant to load the integration. 



## Configuration

1. In Home Assistant, go to **Settings** -> **Devices & Services**.
2. Click **Add Integration** in the bottom-right corner.
3. Search for **Dreame Vacuum (MC1808)**.
4. Fill in the required fields in the configuration form:
   - **Host (IP address)**: The local IP address of your vacuum cleaner.
   - **Token**: The 32-character miIO token of your device.
   - **Name**: Custom name for your entity (e.g., `Dreame Vacuum`).

<p align="center">
  <img src="https://raw.githubusercontent.com/TWOJ_NICK_GITHUB/NAZWA_REPO/main/images/config_flow.png" alt="Dreame MC1808 Configuration Flow">
</p>

5. Click **Submit** and enjoy your fully working vacuum with detailed diagnostic data!


   
