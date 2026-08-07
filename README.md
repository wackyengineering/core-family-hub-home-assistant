# CORE Family Hub for Home Assistant

This custom integration securely connects Home Assistant to
[CORE Family Hub](https://core.wackyengineering.com). The companion makes an
outbound connection; it does not require a public Home Assistant port or a Home
Assistant access token in a browser.

## Install with HACS

1. Install [HACS](https://www.hacs.xyz/docs/use/download/download/) if needed.
2. Add this repository to HACS as an Integration custom repository.
3. Download CORE Family Hub and restart Home Assistant.
4. Open Settings → Devices & services → Add integration → CORE Family Hub.
5. In CORE, open Settings → Integrations → Home Assistant and create a pairing
   code. Enter that code in Home Assistant.

CORE may also provide a My Home Assistant button that opens this repository
directly in HACS.

## Manual recovery installation

Copy `custom_components/core_family_hub` into the Home Assistant config
directory, restart Home Assistant, and add the integration under Devices &
services. HACS is recommended because it also manages updates.

## Supported devices

The integration synchronizes primary lights, switches, fans, climate entities,
sensors, binary sensors, covers, and scenes. Useful diagnostic telemetry is
retained as read-only data for CORE insights, but it is not offered as a device
the household can expose or control. Configuration entities and entities that
are disabled or hidden in Home Assistant stay local and are not sent to CORE.
Owners decide which primary entities CORE may show or control and whether a safe
entity may be controlled from a shared display.

Report integration issues in this repository. CORE application support and
documentation remain at [core.wackyengineering.com](https://core.wackyengineering.com).
